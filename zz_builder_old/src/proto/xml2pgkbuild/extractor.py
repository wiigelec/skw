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

        # Extract global values once
        global_data = {}
        for key, xpath in self.global_fields.items():
            matches = self.tree.xpath(xpath)
            global_data[key] = [str(m) for m in matches]

        results = []
        top_elements = self.tree.xpath(self.top_xpath)

        for elem in top_elements:
            item_data = {}
            for key, xpath in self.field_xpaths.items():
                matches = elem.xpath(xpath)
                item_data[key] = [str(m) for m in matches]

            item_data.update(global_data)  # include shared global fields
            results.append(item_data)

        return results

    def to_yaml(self, data: list) -> str:
        return yaml.dump(data, sort_keys=False, allow_unicode=True)

    def to_json(self, data: list) -> str:
        return json.dumps(data, indent=2, ensure_ascii=False)

def main():
    parser = argparse.ArgumentParser(description="Extract structured XML data using XPath.")
    parser.add_argument("--config", "-c", required=True, help="Path to the TOML config file")
    parser.add_argument("--xml", "-x", required=True, help="Path to the XML file")
    parser.add_argument("--format", choices=["yaml", "json"], default="yaml", help="Output format")

    args = parser.parse_args()

    extractor = XPathExtractor(args.config, args.xml)
    data = extractor.extract()

    if args.format == "json":
        print(extractor.to_json(data))
    else:
        print(extractor.to_yaml(data))

if __name__ == "__main__":
    main()
