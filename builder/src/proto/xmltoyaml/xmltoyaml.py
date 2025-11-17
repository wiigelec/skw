#!/usr/bin/env python3
import toml
import yaml
import argparse
from pathlib import Path
from collections import OrderedDict
from lxml import etree


class TomlXmlToYamlConverter:
    """
    Converts XML + TOML mappings into multiple ordered, pretty YAML files.

    Features:
    - Follows TOML structure and order.
    - Each [section] defines an XPath; child* keys define nested sections.
    - Supports {field} placeholders and {xpath_index} (1-based iteration index).
    - Inherits parent context for placeholder resolution.
    - Generates one YAML file per match of the first section.
    - File names derived from the first two resolved fields.
    - Pretty prints multiline values using | blocks.
    """

    def __init__(self, xml_path: str, toml_path: str, output_dir: str):
        self.xml_path = Path(xml_path)
        self.toml_path = Path(toml_path)
        self.output_dir = Path(output_dir)
        self.toml_data = OrderedDict()
        self.xml_tree = None

    # === MAIN ENTRYPOINT ===
    def convert(self):
        self._load_toml()
        self._load_xml()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._generate_yaml_files()

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
        """Extract values relative to a node; supports {field}, {xpath_index}, and {xpath_index_padded} placeholders."""
        if not xpath_expr or not xpath_expr.strip():
            return ""
    
        # Inject {xpath_index} placeholders (if present in context)
        index_val = context.get("__xpath_index__", "") if context else ""
        int_index = int(index_val) if str(index_val).isdigit() else 0
        padded_index = f"{int_index:04d}"
    
        # Substitute field placeholders
        if context:
            for key, val in context.items():
                if key == "__xpath_index__":
                    continue
                if isinstance(val, list):
                    val = val[0] if val else ""
                safe_val = str(val).replace("'", "&apos;").replace('"', "&quot;")
                xpath_expr = xpath_expr.replace(f"{{{key}}}", safe_val)
    
        # Replace {xpath_index} and {xpath_index_padded}
        if "{xpath_index}" in xpath_expr:
            try:
                formatted_index = f"{int(index_val):04d}"
            except (TypeError, ValueError):
                formatted_index = "0000"
            xpath_expr = xpath_expr.replace("{xpath_index}", f"'{formatted_index}'")
    
        try:
            vals = node.xpath(xpath_expr)
        except etree.XPathEvalError:
            return ""
    
        # Normalize scalar return types
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
    
        # Collapse character lists (from substring or string() results)
        if len(results) > 1 and all(isinstance(x, str) and len(x) == 1 for x in results):
            return "".join(results)
    
        return results if len(results) > 1 else results[0]


    # === SECTION RESOLUTION ===
    def _resolve_section(self, section_name, context_node=None, context=None, index=None):
        """Recursively resolve a section, following TOML order and childN positioning."""
        section = self.toml_data[section_name]
        result = OrderedDict()

        # Merge parent context if any
        if context is None:
            context = {}
        local_context = context.copy()
        local_context["__xpath_index__"] = int(index or context.get("__xpath_index__", 0))

        # Determine which XML nodes to iterate over
        base_xpath = section.get("xpath", "")
        if context_node is not None:
            nodes = [context_node]
        else:
            try:
                nodes = self.xml_tree.xpath(base_xpath) if base_xpath.strip() else [self.xml_tree.getroot()]
            except etree.XPathEvalError:
                nodes = []

        # Handle top-level multi-node logic with enumeration (1-based)
        if context_node is None and nodes and section_name == list(self.toml_data.keys())[0]:
            return [
                self._resolve_section(section_name, node, context, idx + 1)
                for idx, node in enumerate(nodes)
            ]

        node = nodes[0] if nodes else None

        # Follow TOML-defined order
        for key, value in section.items():
            if key == "xpath":
                continue

            if key.startswith("child"):
                for child_name in value:
                    result[child_name] = self._resolve_section(child_name, node, local_context)
            else:
                val = self._extract_value(node, value, local_context) if node is not None else ""
                result[key] = val
                local_context[key] = val  # Make available for placeholder substitution

        return result

    # === OUTPUT GENERATION ===
    def _generate_yaml_files(self):
        top_section = list(self.toml_data.keys())[0]
        entries = self._resolve_section(top_section)
        if not isinstance(entries, list):
            entries = [entries]

        for entry in entries:
            fields = list(entry.keys())
            if len(fields) < 2:
                filename = "entry.yaml"
            else:
                val1 = str(entry.get(fields[0], "") or "unknown")
                val2 = str(entry.get(fields[1], "") or "unknown")
                filename = f"{val1}-{val2}.yaml"
            filename = "".join(c if c.isalnum() or c in "-_." else "_" for c in filename)

            filepath = self.output_dir / filename
            self._write_yaml(entry, filepath)

    # === PRETTY YAML WRITER ===
    def _write_yaml(self, data, filepath):
        """Pretty-print YAML with readable multiline block strings and clean lists."""
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
            """Force block style for lists (avoid inline [a, b, c])"""
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
            yaml.dump(
                clean_data,
                f,
                sort_keys=False,
                allow_unicode=True,
                indent=2,
                width=1000,
                default_flow_style=False,
            )
        print(f"Wrote: {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert XML + TOML mapping into multiple ordered YAML files with placeholder resolution."
    )
    parser.add_argument("xml", help="Path to input XML file.")
    parser.add_argument("toml", help="Path to TOML mapping file.")
    parser.add_argument("output_dir", help="Directory to output YAML files.")
    args = parser.parse_args()

    converter = TomlXmlToYamlConverter(args.xml, args.toml, args.output_dir)
    converter.convert()


if __name__ == "__main__":
    main()
