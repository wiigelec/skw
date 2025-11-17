#!/usr/bin/env python3
import toml
import yaml
import argparse
from pathlib import Path
from collections import OrderedDict
from lxml import etree


class TomlXmlToYamlConverter:
    """
    Converts an XML document into YAML following the structure and order
    defined by a TOML mapping.

    Features:
    - Each [section] may define an XPath selecting nodes.
    - Keys define relative XPaths evaluated on each node.
    - child* arrays embed child sections inline, respecting TOML order.
    - Multiple matches in the first section create separate YAML files.
    - Output file names are derived from the first two field values.
    """

    def __init__(self, xml_path: str, toml_path: str, output_dir: str):
        self.xml_path = Path(xml_path)
        self.toml_path = Path(toml_path)
        self.output_dir = Path(output_dir)
        self.toml_data = OrderedDict()
        self.xml_tree = None

    # --- Core entrypoint ---
    def convert(self):
        self._load_toml()
        self._load_xml()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._generate_yaml_files()

    # --- Loading functions ---
    def _load_toml(self):
        with self.toml_path.open("r", encoding="utf-8") as f:
            self.toml_data = toml.load(f, _dict=OrderedDict)

    def _load_xml(self):
        parser = etree.XMLParser(remove_blank_text=True)
        with self.xml_path.open("r", encoding="utf-8") as f:
            self.xml_tree = etree.parse(f, parser)

    # --- Helper for extracting values from XML ---
    def _extract_value(self, node, xpath_expr):
        if not xpath_expr or not xpath_expr.strip():
            return ""
        try:
            vals = node.xpath(xpath_expr)
        except etree.XPathEvalError:
            return ""
        results = []
        for v in vals:
            if isinstance(v, etree._Element):
                results.append((v.text or "").strip())
            elif isinstance(v, (str, int, float)):
                results.append(str(v).strip())
        if not results:
            return ""
        return results if len(results) > 1 else results[0]

    # --- Recursive TOML-driven builder ---
    def _resolve_section(self, section_name, context_node=None):
        section = self.toml_data[section_name]
        result = OrderedDict()

        # Determine which nodes to iterate over
        base_xpath = section.get("xpath", "")
        if context_node is not None:
            nodes = [context_node]
        else:
            try:
                nodes = self.xml_tree.xpath(base_xpath) if base_xpath.strip() else [self.xml_tree.getroot()]
            except etree.XPathEvalError:
                nodes = []

        # If this is the top-level section, build a list of entries
        if context_node is None and nodes and section_name == list(self.toml_data.keys())[0]:
            return [self._resolve_section(section_name, node) for node in nodes]

        node = nodes[0] if nodes else None

        # Walk through TOML keys in order, respecting childN position
        for key, value in section.items():
            if key == "xpath":
                continue
            if key.startswith("child"):
                for child_name in value:
                    result[child_name] = self._resolve_section(child_name, node)
            else:
                result[key] = self._extract_value(node, value) if node is not None else ""

        return result

    # --- Multi-file generation ---
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

    # --- YAML writer ---
    def _write_yaml(self, data, filepath):
        """Pretty-print YAML with readable multiline and indentation."""
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
            """Represent multiline strings with '|' literal block style."""
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    
        def prepare_literals(obj):
            """Recursively wrap multiline strings in LiteralString for YAML output."""
            if isinstance(obj, str) and "\n" in obj:
                return LiteralString(obj)
            elif isinstance(obj, list):
                return [prepare_literals(x) for x in obj]
            elif isinstance(obj, dict):
                return {k: prepare_literals(v) for k, v in obj.items()}
            return obj
    
        yaml.add_representer(LiteralString, literal_representer)
    
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
        description="Convert XML + TOML mapping into multiple ordered YAML files."
    )
    parser.add_argument("xml", help="Path to input XML file.")
    parser.add_argument("toml", help="Path to TOML mapping file.")
    parser.add_argument("output_dir", help="Directory to output YAML files.")
    args = parser.parse_args()

    converter = TomlXmlToYamlConverter(args.xml, args.toml, args.output_dir)
    converter.convert()


if __name__ == "__main__":
    main()
