#!/usr/bin/env python3
"""
TomlToYamlXPathConverter

Converts a TOML configuration template into structured YAML data using:
- Package list from a JSON file.
- Metadata extracted from an XML source using XPath expressions.
- Ordered key preservation and recursive child embedding.
"""

import toml
import json
import yaml
import argparse
from lxml import etree
from pathlib import Path
from collections import OrderedDict


class TomlToYamlXPathConverter:
    """
    Converts a TOML + XML + JSON configuration into structured YAML.

    Workflow:
      1. Load TOML template.
      2. Load XML source.
      3. Load JSON package list.
      4. For each package:
         - Locate matching XML node by name/version.
         - Resolve all XPath expressions defined in TOML relative to that node.
         - Recursively embed child sections.
      5. Write final list as YAML preserving key order.
    """

    def __init__(self, input_toml_path: str, output_yaml_path: str, xml_path: str, input_json_path: str):
        self.input_toml_path = Path(input_toml_path)
        self.output_yaml_path = Path(output_yaml_path)
        self.xml_path = Path(xml_path)
        self.input_json_path = Path(input_json_path)

        self.toml_data = OrderedDict()
        self.xml_root = None
        self.package_list = []

        # Load essential data sources
        self._load_toml()
        self._load_xml(self.xml_path)
        self._load_package_list(self.input_json_path)

    # ---------------------------
    # Data Loading
    # ---------------------------

    def _load_toml(self):
        """Load TOML configuration into an OrderedDict."""
        with self.input_toml_path.open("r", encoding="utf-8") as f:
            self.toml_data = toml.load(f, _dict=OrderedDict)

    def _load_xml(self, xml_path: Path):
        """Parse the XML file and store root."""
        tree = etree.parse(str(xml_path))
        self.xml_root = tree.getroot()

    def _load_package_list(self, json_path: Path):
        """Load list of packages from a JSON file."""
        with json_path.open("r", encoding="utf-8") as f:
            self.package_list = json.load(f)
        if not isinstance(self.package_list, list):
            raise ValueError("Input JSON must be a list of package objects.")

    # ---------------------------
    # Extraction Logic
    # ---------------------------

    def _find_xml_package_node(self, package_name: str, package_version: str):
        """
        Find the XML node matching the package name and version.
        Example XPath:
            .//package[name='mypkg' and version='1.0']
        """
        xpath_expr = f".//package[name='{package_name}' and version='{package_version}']"
        matches = self.xml_root.xpath(xpath_expr)
        return matches[0] if matches else None

    def _execute_xpath(self, node, xpath_expression: str) -> str:
        """Execute an XPath relative to a given XML node."""
        try:
            result = node.xpath(xpath_expression)
            if isinstance(result, list):
                if len(result) == 0:
                    return ""
                # Return stringified first item if nodes, else joined text
                first = result[0]
                if isinstance(first, etree._Element):
                    return first.text or ""
                return " ".join(str(r) for r in result)
            return str(result)
        except Exception as e:
            return f"[XPathError: {e}]"

    # ---------------------------
    # Recursive Structure Building
    # ---------------------------

    def _resolve_children(self, node: OrderedDict, xml_context_node) -> OrderedDict:
        """
        Recursively resolve TOML structure using XML node context.
        - Child references (child1, child2, ...) are expanded.
        - String values are treated as XPath expressions.
        """
        result = OrderedDict()

        for key, value in node.items():
            # Resolve child tables
            if key.startswith("child"):
                for child_name in value:
                    if child_name in self.toml_data:
                        result[child_name] = self._resolve_children(self.toml_data[child_name], xml_context_node)
                continue

            # Nested dicts (explicit subtables)
            if isinstance(value, dict):
                result[key] = self._resolve_children(value, xml_context_node)
                continue

            # String values → treat as XPath
            if isinstance(value, str) and value.strip().startswith(("/", ".", "..")):
                result[key] = self._execute_xpath(xml_context_node, value)
            else:
                result[key] = value

        return result

    def _is_child(self, section_name: str) -> bool:
        """Return True if this section is referenced as a child elsewhere."""
        for content in self.toml_data.values():
            for key, value in content.items():
                if key.startswith("child") and section_name in value:
                    return True
        return False

    def _build_structure(self):
        """
        Build the final YAML-ready list of OrderedDicts.
        Each package from JSON drives one item.
        """
        results = []
        for pkg in self.package_list:
            name = pkg.get("name")
            version = pkg.get("version")
            if not name or not version:
                continue

            xml_node = self._find_xml_package_node(name, version)
            if xml_node is None:
                continue

            # Start from top-level non-child sections
            item = OrderedDict()
            for section, content in self.toml_data.items():
                if self._is_child(section):
                    continue
                item[section] = self._resolve_children(content, xml_node)

            results.append(item)
        return results

    # ---------------------------
    # Output
    # ---------------------------

    def _write_yaml(self, data):
        """Write the final structure as YAML."""
        with self.output_yaml_path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, indent=2, sort_keys=False)
        print(f"✅ YAML written to: {self.output_yaml_path}")

    # ---------------------------
    # Public API
    # ---------------------------

    def convert(self):
        """Run the full conversion pipeline."""
        data = self._build_structure()
        self._write_yaml(data)


# ---------------------------
# Command-Line Wrapper
# ---------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert TOML + XML + JSON to structured YAML via XPath lookups."
    )
    parser.add_argument("toml", help="Path to input TOML configuration.")
    parser.add_argument("xml", help="Path to source XML file.")
    parser.add_argument("json", help="Path to input JSON package list.")
    parser.add_argument("yaml", help="Path to output YAML file.")

    args = parser.parse_args()

    converter = TomlToYamlXPathConverter(
        input_toml_path=args.toml,
        output_yaml_path=args.yaml,
        xml_path=args.xml,
        input_json_path=args.json,
    )
    converter.convert()


if __name__ == "__main__":
    main()
