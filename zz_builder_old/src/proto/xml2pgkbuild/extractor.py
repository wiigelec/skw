import argparse
import toml
import yaml
import json
from lxml import etree


class XPathExtractor:
    def __init__(self, toml_config_path: str, xml_path: str):
        self.config_path = toml_config_path
        self.xml_path = xml_path
        self.config = self._load_config()
        self.tree = self._load_xml()
        self.top_xpath = self.config.get("top_xpath", None)
        self.field_xpaths = self.config.get("fields", {})
        self.global_fields = self.config.get("global_fields", {})

    def _load_config(self) -> dict:
        with open(self.config_path, 'r') as f:
            return toml.load(f)

    def _load_xml(self):
        with open(self.xml_path, 'rb') as f:
            return etree.parse(f)

    def extract(self) -> list:
        if not self.top_xpath:
            raise ValueError("Missing [top_xpath] in config")

        results = []
        top_elements = self.tree.xpath(self.top_xpath)

        for elem in top_elements:
            item_data = {}
            for key, xpath in self.field_xpaths.items():
                matches = elem.xpath(xpath)

                # Join build_commands into multiline string with visible newlines
                if key == "build_commands":
                    item_data[key] = "\n".join(str(m) for m in matches)
                else:
                    item_data[key] = [str(m) for m in matches]

            results.append(item_data)

        return results

    def to_yaml(self, data: list) -> str:
        return yaml.dump(data, sort_keys=False, allow_unicode=True)

    def to_json(self, data: list) -> str:
        # Custom JSON encoder that keeps newlines visible
        return json.dumps(data, indent=2, ensure_ascii=False)

def main():
    parser = argparse.ArgumentParser(description="Extract structured XML data using XPath and format build_commands.")
    parser.add_argument("--config", "-c", required=True, help="Path to the TOML config file")
    parser.add_argument("--xml", "-x", required=True, help="Path to the XML file")
    parser.add_argument("--format", choices=["yaml", "json"], default="json", help="Output format")

    args = parser.parse_args()

    extractor = XPathExtractor(args.config, args.xml)
    data = extractor.extract()

    if args.format == "json":
        formatted = extractor.to_json(data)
        # Replace escaped newlines (\n) with real ones for readability
        formatted = formatted.replace("\\n", "\n")
        print(formatted)
    else:
        print(extractor.to_yaml(data))


if __name__ == "__main__":
    main()

# python3 extractor.py --config extractor.toml --xml lfs-full.xml --format yaml | sed '/.* pkgname.*/d' | sed 's/.*- //g' | sed 's/.*/\L&/g'
