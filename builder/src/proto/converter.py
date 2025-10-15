#!/usr/bin/env python3
import toml
import json
import argparse
from pathlib import Path
from collections import OrderedDict


class TomlToJsonConverter:
    """
    Converts a TOML configuration file into a nested JSON structure.

    - Supports 'child*' arrays that reference other top-level tables.
    - Merges those referenced tables as nested objects inside their parent.
    - Preserves the original TOML key order.
    """

    def __init__(self, input_path: str, output_path: str):
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.toml_data = OrderedDict()

    def convert(self):
        """Perform the conversion process."""
        self._load_toml()
        result = self._build_structure()
        self._write_json(result)

    def _load_toml(self):
        """Load TOML preserving order."""
        with self.input_path.open("r", encoding="utf-8") as f:
            self.toml_data = toml.load(f, _dict=OrderedDict)

    def _resolve_children(self, node):
        """
        Recursively replaces child references with their corresponding tables.
        """
        result = OrderedDict()

        for key, value in node.items():
            if key.startswith("child"):
                # e.g. child1 = ["source"]
                for child_name in value:
                    if child_name in self.toml_data:
                        result[child_name] = self._resolve_children(self.toml_data[child_name])
                continue

            if isinstance(value, dict):
                result[key] = self._resolve_children(value)
            else:
                result[key] = value

        return result

    def _build_structure(self):
        """
        Build the final JSON structure, embedding child tables.
        Only top-level parents remain at the root.
        """
        result = OrderedDict()

        for section, content in self.toml_data.items():
            # Skip tables that are referenced as children
            if self._is_child(section):
                continue

            result[section] = self._resolve_children(content)

        return result

    def _is_child(self, section_name):
        """Check if this section is referenced as a child somewhere."""
        for content in self.toml_data.values():
            for key, value in content.items():
                if key.startswith("child") and section_name in value:
                    return True
        return False

    def _write_json(self, data):
        """Write the final structured JSON."""
        with self.output_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"? JSON written to: {self.output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert TOML to JSON, embedding referenced child tables."
    )
    parser.add_argument("input", help="Path to input TOML file.")
    parser.add_argument("output", help="Path to output JSON file.")
    args = parser.parse_args()

    converter = TomlToJsonConverter(args.input, args.output)
    converter.convert()


if __name__ == "__main__":
    main()
