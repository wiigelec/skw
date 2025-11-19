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

def represent_ordereddict(dumper, data):
    return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())

yaml.add_representer(OrderedDict, represent_ordereddict)


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
        self._index_packages()
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
        """Load list of packages from JSON file. Supports both top-level list and dict formats."""
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    
        if isinstance(data, dict):
            # Expect a key "packages" holding the list
            packages = data.get("packages")
            if not isinstance(packages, list):
                raise ValueError("JSON object must contain a 'packages' list field.")
            self.package_list = packages
        elif isinstance(data, list):
            self.package_list = data
        else:
            raise ValueError("Input JSON must be either a list or an object containing 'packages'.")
    
        # Sanity check
        for pkg in self.package_list:
            if not isinstance(pkg, dict) or "name" not in pkg or "version" not in pkg:
                raise ValueError(f"Invalid package entry: {pkg}")

    # ---------------------------
    # Extraction Logic
    # ---------------------------

    def _find_xml_package_node(self, package_name: str, package_version: str):
        key = f"{package_name.lower()}-{package_version}"
        node = self.package_index.get(key)
        if node is not None:
            return node
        print(f"[WARN] No XML node found for {package_name}-{package_version}")
        return None

    def _execute_xpath(self, node: etree._Element, xpath_expression: str, package_name: str = None, package_version: str = None) -> str:
        """
        Executes an XPath expression relative to the given XML node.
        Supports dynamic variable substitution using {name} and {version} placeholders.
        """
        try:
            expr = xpath_expression
    
            # --- Variable substitution for TOML placeholders ---
            if "{name}" in expr or "{version}" in expr:
                expr = expr.format(
                    name=package_name or "",
                    version=package_version or ""
                )
    
            #print(f"xpath: {expr}")
    
            # --- Determine context (absolute vs relative) ---
            context = self.xml_root if expr.strip().startswith("//") else node
            result = context.xpath(expr)
    
            # --- Convert output to a clean string if possible ---
            if not result:
                return ""
            if isinstance(result, list):
                # Join multi-values into one string, separated by space
                return " ".join(str(r).strip() for r in result if str(r).strip())
            return str(result).strip()
    
        except Exception as e:
            print(f"[WARN] XPath lookup failed for expression '{xpath_expression}': {e}")
            return ""


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
            # Skip internal or structural keys
            if key in ("context_xpath", "package_xpath"):
                continue
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

            # String values treat as XPath
            if isinstance(value, str) and value.strip().startswith(("/", ".", "..")):
                #print(f"xpath: {value}")
                result[key] = self._execute_xpath(
                    xml_context_node,
                    value,
                    package_name=self.current_package_name,
                    package_version=self.current_package_version
                )
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
        print(f"Iterating package list...")
        for pkg in self.package_list:
            name = pkg.get("name")
            version = pkg.get("version")
            self.current_package_name = name
            self.current_package_version = version
            
            print(f"{name}--{version}")

            if not name or not version:
                continue

            xml_node = self._find_xml_package_node(name, version)
            if xml_node is None:
                print(f"NO XML NODE FOUND")
                continue

            # Start from top-level non-child sections
            item = OrderedDict()
            for section, content in self.toml_data.items():
                if section == "lookup" or self._is_child(section):
                    continue
                if self._is_child(section):
                    continue
                item[section] = self._resolve_children(content, xml_node)

            results.append(item)
        return results
        
    def _index_packages(self):
        """
        Build a lookup dictionary of XML nodes by normalized name-version keys,
        using XPaths defined in the TOML [package] section.
        """
        self.package_index = {}
        print("[INFO] Building XML package index from TOML configuration...")
    
        # Load package discovery rules from TOML
        pkg_cfg = self.toml_data.get("package")
        if not pkg_cfg:
            raise ValueError("TOML must contain a [package] section with 'context_xpath', 'name', and 'version'.")
    
        context_xpath = pkg_cfg.get("context_xpath")
        name_xpath = pkg_cfg.get("name")
        version_xpath = pkg_cfg.get("version")
    
        if not context_xpath or not name_xpath or not version_xpath:
            raise ValueError("[package] section must define 'context_xpath', 'name', and 'version' XPaths.")
    
        # Find all context nodes
        package_nodes = self.xml_root.xpath(context_xpath)
        print(f"[INFO] Found {len(package_nodes)} package context nodes via {context_xpath}")
    
        # Extract name/version for each node
        for node in package_nodes:
            name = self._execute_xpath(node, name_xpath)
            version = self._execute_xpath(node, version_xpath)
            if not name:
                continue
            key = f"{name.lower()}-{version}"
            self.package_index[key] = node
    
        print(f"[INFO] Indexed {len(self.package_index)} packages.")

        
    # ---------------------------
    # Output
    # ---------------------------

    def _write_yaml(self, data, package_name: str, package_version: str):
        """Write a single package structure as YAML in the output directory."""
        # Ensure output directory exists
        self.output_yaml_path.mkdir(parents=True, exist_ok=True)

        # Safe filename
        filename = f"{package_name}-{package_version}.yaml".replace("/", "_")
        output_path = self.output_yaml_path / filename

        with output_path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, indent=2, sort_keys=False)

        print(f"[INFO] YAML written: {output_path}")

    # ---------------------------
    # Public API
    # ---------------------------

    def convert(self):
        """Run the full conversion pipeline and write one YAML per package."""
        print("[INFO] Starting per-package YAML generation...")
        for pkg in self.package_list:
            name = pkg.get("name")
            version = pkg.get("version")
            if not name or not version:
                continue

            xml_node = self._find_xml_package_node(name, version)
            if xml_node is None:
                print(f"[WARN] No XML node found for {name}-{version}")
                continue

            # --- Set current package context (needed for XPath placeholders) ---
            self.current_package_name = name
            self.current_package_version = version

            # --- Build data for this package ---
            package_data = OrderedDict()
            for section, content in self.toml_data.items():
                if section == "lookup" or self._is_child(section):
                    continue
                package_data[section] = self._resolve_children(content, xml_node)

            # --- Write individual YAML ---
            self._write_yaml(package_data, name, version)


# ---------------------------
# Command-Line Wrapper
# ---------------------------

def main():
    parser = argparse.ArgumentParser(
    description="Convert TOML + XML + JSON to structured YAML files per package."
    )
    parser.add_argument("toml", help="Path to input TOML configuration.")
    parser.add_argument("xml", help="Path to source XML file.")
    parser.add_argument("json", help="Path to input JSON package list.")
    parser.add_argument("outdir", help="Directory to write YAML files into.")
    
    args = parser.parse_args()
    
    converter = TomlToYamlXPathConverter(
        input_toml_path=args.toml,
        output_yaml_path=Path(args.outdir),  # now directory
        xml_path=args.xml,
        input_json_path=args.json,
    )
    converter.convert()


if __name__ == "__main__":
    main()
