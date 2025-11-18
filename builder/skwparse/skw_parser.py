#!/usr/bin/env python3
import os
import toml
import yaml
from pathlib import Path
from collections import OrderedDict
from lxml import etree


class SKWParser:
    """
    SKWParser — Modern TOML–XML–YAML parser for ScratchKit Builder.

    This parser replaces the legacy XML→JSON parser and automatically:
    - Loads book XML (from build_dir/books/<book>/book.xml)
    - Loads parser mapping TOML (from profiles/<book>/<profile>/parser_map.toml)
    - Converts XML into multiple ordered YAML files according to TOML mappings.
    """

    def __init__(self, build_dir, profiles_dir, book, profile):
        self.build_dir = Path(build_dir)
        self.profiles_dir = Path(profiles_dir)
        self.book = book
        self.profile = profile

        # Resolve default paths
        self.xml_path = self.build_dir / "books" / book / "book.xml"
        self.toml_path = self.profiles_dir / book / profile / "parser_map.toml"
        self.output_dir = self.build_dir / "parser" / book / profile

        # Validate environment
        if not self.xml_path.exists():
            raise FileNotFoundError(
                f"[SKWParser] XML not found at {self.xml_path}. Did you run install-book?"
            )
        if not self.toml_path.exists():
            raise FileNotFoundError(
                f"[SKWParser] parser_map.toml not found for {book}/{profile}."
            )

        # Load configuration and XML
        self.toml_data = OrderedDict()
        self.xml_tree = None

    # === ENTRYPOINT ===
    def run(self):
        print(f"[SKWParser] Running parser for book '{self.book}', profile '{self.profile}'")
        self._load_toml()
        self._load_xml()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._generate_yaml_files()
        print(f"[SKWParser] Completed. YAML outputs in {self.output_dir}")

    # === LOADERS ===
    def _load_toml(self):
        with self.toml_path.open("r", encoding="utf-8") as f:
            self.toml_data = toml.load(f, _dict=OrderedDict)

    def _load_xml(self):
        parser = etree.XMLParser(remove_blank_text=True)
        with self.xml_path.open("r", encoding="utf-8") as f:
            self.xml_tree = etree.parse(f, parser)

    # === VALUE EXTRACTION ===
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

    # === SECTION RESOLUTION ===
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

            if key.startswith("child"):
                for child_name in value:
                    result[child_name] = self._resolve_section(child_name, node, local_context)
            else:
                val = self._extract_value(node, value, local_context) if node is not None else ""
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

    # === YAML OUTPUT ===
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
            self._write_yaml(entry, filepath)

    def _write_yaml(self, data, filepath):
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
        print(f"[SKWParser] Wrote: {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert XML + TOML mapping into ordered YAML build blueprints."
    )
    parser.add_argument("xml", help="Path to input XML file.")
    parser.add_argument("toml", help="Path to TOML mapping file.")
    parser.add_argument("output_dir", help="Directory to output YAML files.")
    args = parser.parse_args()

    skw_parser = SKWParser(args.xml, args.toml, args.output_dir)
    skw_parser.convert()
  

if __name__ == "__main__":
    main()
