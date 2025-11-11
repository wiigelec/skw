"""
xml_package_extractor.py
------------------------

Implements the XMLPackageExtractor class and a command-line wrapper.

Reads configuration from a TOML file, extracts package data from an XML source
using XPath-like patterns, and outputs structured results to JSON.

Example usage:
    python xml_package_extractor.py extract --xml book.xml --config config.toml --out packages.json
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # For older Python versions


class XMLPackageExtractor:
    """Extracts package data from an XML document based on TOML-configured XPath rules."""

    def __init__(self, xml_file_path: str, output_json_path: str, config_file_path: str):
        self.xml_file_path = xml_file_path
        self.output_json_path = output_json_path
        self.config_file_path = config_file_path

        self.book_id = None
        self.package_node_xpath = None
        self.package_name_xpath = None
        self.package_version_xpath = None

        print(f"[INIT] XMLPackageExtractor initialized with:")
        print(f"       XML: {xml_file_path}")
        print(f"       Config: {config_file_path}")
        print(f"       Output: {output_json_path}")

        self._load_config(config_file_path)

    # -----------------------------------------------------------
    # CONFIG LOADING
    # -----------------------------------------------------------
    def _load_config(self, config_file_path: str):
        """Reads and validates configuration from a TOML file."""
        try:
            if tomllib.__name__ == "tomllib":
                with open(config_file_path, "rb") as f:
                    config = tomllib.load(f)
            else:
                with open(config_file_path, "r", encoding="utf-8") as f:
                    config = tomllib.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {config_file_path}")
        except Exception as e:
            raise ValueError(f"Failed to parse configuration: {e}")

        try:
            book_cfg = config["book"]
            pkg_cfg = config["package"]
        except KeyError as e:
            raise KeyError(f"Missing required section in config: {e}")

        for key in ["id"]:
            if key not in book_cfg:
                raise KeyError(f"Missing key [book].{key} in configuration")

        for key in ["node_xpath", "name_xpath", "version_xpath"]:
            if key not in pkg_cfg:
                raise KeyError(f"Missing key [package].{key} in configuration")

        self.book_id = book_cfg["id"]
        self.package_node_xpath = pkg_cfg["node_xpath"]
        self.package_name_xpath = pkg_cfg["name_xpath"]
        self.package_version_xpath = pkg_cfg["version_xpath"]

        print(f"[CONFIG] Loaded configuration for book: '{self.book_id}'")

    # -----------------------------------------------------------
    # XML LOADING
    # -----------------------------------------------------------
    def _load_xml(self):
        """Parses the XML file and returns the root element."""
        try:
            tree = ET.parse(self.xml_file_path)
            return tree.getroot()
        except FileNotFoundError:
            raise FileNotFoundError(f"XML file not found: {self.xml_file_path}")
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse XML file: {e}")

    # -----------------------------------------------------------
    # VALUE EXTRACTION
    # -----------------------------------------------------------
    def _extract_value(self, element: ET.Element, xpath: str) -> str:
        """
        Extracts a value using an XPath-like expression.

        Supports:
          - Attributes (./@attr)
          - Element text (./child)
        """
        if not xpath:
            return None

        xpath = xpath.strip()
        if xpath.startswith("./@"):  # attribute extraction
            attr_name = xpath.replace("./@", "", 1)
            return element.attrib.get(attr_name, None)

        found = element.find(xpath)
        if found is not None and found.text:
            return found.text.strip()
        return None

    # -----------------------------------------------------------
    # MAIN EXTRACTION LOGIC
    # -----------------------------------------------------------
    def extract_and_save(self) -> Dict[str, Any]:
        """Main public method to perform extraction and save to JSON."""
        root = self._load_xml()
        print(f"[XML] Loaded XML root: {root.tag}")

        packages_data: List[Dict[str, Any]] = []

        nodes = root.findall(self.package_node_xpath)
        print(f"[XML] Found {len(nodes)} package nodes using: {self.package_node_xpath}")

        for i, pkg_node in enumerate(nodes, start=1):
            name = self._extract_value(pkg_node, self.package_name_xpath) or "N/A"
            version = self._extract_value(pkg_node, self.package_version_xpath) or "N/A"
            print(f"[PKG] {i}. name={name}, version={version}")
            packages_data.append({"name": name, "version": version})

        output = {"book_id": self.book_id, "packages": packages_data}

        with open(self.output_json_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"[JSON] Saved extracted data to {self.output_json_path}")
        print(f"[DONE] Extracted {len(packages_data)} packages.")
        return output


# -----------------------------------------------------------
# CLI WRAPPER
# -----------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        prog="xml-package-extractor",
        description="Extracts package data from XML using configurable TOML rules."
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Extract subcommand
    extract_parser = subparsers.add_parser("extract", help="Run the XML extraction process")
    extract_parser.add_argument("--xml", required=True, help="Path to the input XML file")
    extract_parser.add_argument("--config", required=True, help="Path to the TOML configuration file")
    extract_parser.add_argument("--out", required=True, help="Path to the output JSON file")

    args = parser.parse_args()

    if args.command == "extract":
        try:
            extractor = XMLPackageExtractor(args.xml, args.out, args.config)
            extractor.extract_and_save()
            sys.exit(0)
        except Exception as e:
            print(f"[ERROR] {e}")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
