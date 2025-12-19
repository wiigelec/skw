#!/usr/bin/env python3
# ================================================================
#
# skw_parser.py
#
# ================================================================

import os
import toml
import yaml
from pathlib import Path
from collections import OrderedDict
from lxml import etree
from pathlib import Path

#------------------------------------------------------------------#
class SKWParser:
    """
    SKWParser — Modern TOML-XML-YAML parser for ScratchKit Builder.

    This parser replaces the legacy XML?JSON parser and automatically:
    - Loads book XML (from build_dir/books/<book>/book.xml)
    - Loads parser mapping TOML (from profiles/<book>/<profile>/parser_map.toml)
    - Converts XML into multiple ordered YAML files according to TOML mappings.
    """

    #------------------------------------------------------------------#
    def __init__(self, build_dir, profiles_dir, book):
        self.build_dir = Path(build_dir)
        self.profiles_dir = Path(profiles_dir)
        self.book = book

        # Get xml path from config
        self.config_path = self.profiles_dir / book / "skwparser.toml"
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"[SKWParser] {self.config_path} not found. Did you copy an example config?"
            )
        with open(self.config_path, "r", encoding="utf-8") as f:
            cfg = toml.load(f)
        raw_xml_path = cfg["main"]["xml_path"].format(book=self.book)
        self.xml_path = Path(raw_xml_path).expanduser().resolve()
        if not self.xml_path.exists():
            raise FileNotFoundError(
                f"[SKWParser] XML not found at {self.xml_path}. Did you run install-book?"
            )

        # Get parser config
        self.toml_path = self.config_path
        if not self.toml_path.exists():
            raise FileNotFoundError(
                f"[SKWParser] parser_map.toml not found for {book}/{profile}."
            )

        # Get output dir
        raw_out_dir = cfg["main"]["output_dir"].format(book=self.book)
        self.output_dir = Path(raw_out_dir).expanduser().resolve()
        
        # Load configuration and XML
        self.toml_data = OrderedDict()
        self.xml_tree = None

    #------------------------------------------------------------------#
    def run(self):
        print(f"[SKWParser] Running parser for book '{self.book}'")
        self._load_toml()
        self._load_xml()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._generate_yaml_files()
        print(f"[SKWParser] Completed. YAML outputs in {self.output_dir}")

    #------------------------------------------------------------------#
    def _load_toml(self):
        with self.toml_path.open("r", encoding="utf-8") as f:
            self.toml_data = toml.load(f, _dict=OrderedDict)

    #------------------------------------------------------------------#
    def _load_xml(self):
        parser = etree.XMLParser(remove_blank_text=True)
        with self.xml_path.open("r", encoding="utf-8") as f:
            self.xml_tree = etree.parse(f, parser)

    #------------------------------------------------------------------#
    def _extract_value(self, node, xpath_expr, context=None):
        """Extract values relative to a node; supports placeholders like {field} and {xpath_index}."""
        if not xpath_expr or not xpath_expr.strip():
            return ""

        if node is None:
            return ""

        index_val = context.get("__xpath_index__", "") if context else ""
        int_index = int(index_val) if str(index_val).isdigit() else 0
        padded_index = f"{int_index:04d}"

        # Substitute placeholders
        if context:
            for key, val in context.items():
                if key == "__xpath_index__":
                    continue
                if isinstance(val, list):
                    val = val[0] if val else ""
                safe_val = str(val).replace("'", "&apos;").replace('"', "&quot;")
                xpath_expr = xpath_expr.replace(f"{{{key}}}", safe_val)

        if "{xpath_index}" in xpath_expr:
            xpath_expr = xpath_expr.replace("{xpath_index}", f"'{padded_index}'")

        try:
            vals = node.xpath(xpath_expr)
        except etree.XPathEvalError:
            return ""

        if isinstance(vals, (str, int, float)):
            vals = [str(vals)]
        elif isinstance(vals, bool):
            vals = [str(vals).lower()]

        results = []
        for v in vals:
            if isinstance(v, etree._Element):
                results.append((v.text or "").strip())
            elif isinstance(v, (str, int, float)):
                results.append(str(v).strip())

        if not results:
            return ""
        if len(results) > 1 and all(isinstance(x, str) and len(x) == 1 for x in results):
            return "".join(results)
        return results if len(results) > 1 else results[0]

    #------------------------------------------------------------------#
    def _resolve_section(self, section_name, context_node=None, context=None, index=None):
        """Recursively resolve TOML-defined section into nested YAML data."""
        section = self.toml_data[section_name]
        result = OrderedDict()

        context = context or {}
        local_context = context.copy()
        local_context["__xpath_index__"] = int(index or context.get("__xpath_index__", 0))

        base_xpath = section.get("xpath", "")
        if context_node is not None:
            nodes = [context_node]
        else:
            try:
                nodes = self.xml_tree.xpath(base_xpath) if base_xpath.strip() else [self.xml_tree.getroot()]
            except etree.XPathEvalError:
                nodes = []

        if context_node is None and nodes and section_name == list(self.toml_data.keys())[0]:
            return [
                self._resolve_section(section_name, node, context, idx + 1)
                for idx, node in enumerate(nodes)
            ]

        node = nodes[0] if nodes else None

        for key, value in section.items():
            if key == "xpath":
                continue
        
            # Child sections recurse
            if key.startswith("child"):
                for child_name in value:
                    result[child_name] = self._resolve_section(child_name, node, local_context)
                continue
        
            # --- Determine chapter and section IDs ---
            chap_id = node.get("id") if node is not None and node.tag.lower() == "chapter" else local_context.get("chapter_id")
            sec_id = node.get("id") if node is not None and node.tag.lower() == "section" else local_context.get("section_id")
            local_context["chapter_id"] = chap_id
            local_context["section_id"] = sec_id
        
            # --- Determine XPath expression using override hierarchy ---
            xpath_expr = self._get_xpath_expr(sec_id, chap_id, key) or value
            
            # Apply explicit blank overrides (e.g., "source.url" = "")
            override_expr = self._get_xpath_expr(local_context.get("section_id"), local_context.get("chapter_id"), f"{section_name}.{key}")
            if override_expr == "":
                result[key] = ""
                continue
        
            val = self._extract_value(node, xpath_expr, local_context) if node is not None else ""
            result[key] = val
            local_context[key] = val

        # Postprocess name/version logic
        if "name_version" in result and isinstance(result["name_version"], str):
            nv = result["name_version"].strip()
            n, v = (nv.rsplit("-", 1) + [""])[:2] if "-" in nv else (nv, "")
            n, v = n.strip(), v.strip().split(" ", 1)[0] if " " in v else v
            local_context["name"], local_context["version"] = n, v
            result["name_version"] = nv

            for field, xpath_expr in section.items():
                if not isinstance(xpath_expr, str):
                    continue
                if "{" in xpath_expr and ("{name}" in xpath_expr or "{version}" in xpath_expr):
                    new_val = self._extract_value(node, xpath_expr, local_context)
                    if new_val:
                        result[field] = new_val

        return result
        
    #------------------------------------------------------------------#
    def _get_xpath_expr(self, section_id, chapter_id, key):
        """Retrieve an XPath expression with section/chapter/global fallback.
        Supports nested override keys like 'source.url'."""
        def resolve_nested(cfg, dotted_key):
            """Resolve nested keys such as 'source.url' inside a dict."""
            if not isinstance(cfg, dict):
                return None
            if dotted_key in cfg:
                return cfg[dotted_key]
            # Walk through nested structures
            parts = dotted_key.split(".")
            cur = cfg
            for part in parts:
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return None
            return cur if isinstance(cur, str) else None

        # Try section-level overrides
        if section_id in self.toml_data:
            sec_cfg = self.toml_data[section_id].get("xpaths", {})
            val = resolve_nested(sec_cfg, key)
            if val is not None:
                return val

        # Try chapter-level overrides
        if chapter_id in self.toml_data:
            chap_cfg = self.toml_data[chapter_id].get("xpaths", {})
            val = resolve_nested(chap_cfg, key)
            if val is not None:
                return val

        # Try global-level overrides
        if "xpaths" in self.toml_data:
            val = resolve_nested(self.toml_data["xpaths"], key)
            if val is not None:
                return val

        return None
   
    #------------------------------------------------------------------#
    def _generate_yaml_files(self):
        top_section = list(self.toml_data.keys())[0]
        entries = self._resolve_section(top_section)
        if not isinstance(entries, list):
            entries = [entries]

        for entry in entries:
            fields = list(entry.keys())
            val1 = str(entry.get(fields[0], "") or "unknown")
            val2 = str(entry.get(fields[1], "") or "unknown")
            filename = f"{val1}-{val2}.yaml"
            filename = "".join(c if c.isalnum() or c in "-_." else "_" for c in filename)
            filepath = self.output_dir / filename
            self._write_yaml(entry, filepath, filename)

    #------------------------------------------------------------------#
    def _write_yaml(self, data, filepath, filename):
        def to_dict(obj):
            if isinstance(obj, OrderedDict):
                return {k: to_dict(v) for k, v in obj.items()}
            elif isinstance(obj, dict):
                return {k: to_dict(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [to_dict(x) for x in obj]
            else:
                return obj

        class LiteralString(str): pass

        def literal_representer(dumper, data):
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")

        def sequence_representer(dumper, data):
            return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=False)

        yaml.add_representer(LiteralString, literal_representer)
        yaml.add_representer(list, sequence_representer)

        def prepare_literals(obj):
            if isinstance(obj, str) and "\n" in obj:
                return LiteralString(obj)
            elif isinstance(obj, list):
                return [prepare_literals(x) for x in obj]
            elif isinstance(obj, dict):
                return {k: prepare_literals(v) for k, v in obj.items()}
            return obj

        clean_data = prepare_literals(to_dict(data))
        with filepath.open("w", encoding="utf-8") as f:
            yaml.dump(clean_data, f, sort_keys=False, allow_unicode=True, indent=2, width=1000)
        print(f"[SKWParser] Wrote: {filename}")
