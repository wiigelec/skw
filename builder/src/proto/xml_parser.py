import tomllib
import json
from lxml import etree


def load_config(config_file: str) -> dict:
    with open(config_file, "rb") as f:
        return tomllib.load(f)


def extract_node(node, rule_name: str, config: dict, debug: bool = False):
    rules = config["xpaths"][rule_name]
    result = {}

    for key, value in rules.items():
        if key == "xpath":
            continue

        # Child collection (look for nested .xpath)
        if isinstance(value, dict) and "xpath" in value:
            child_xpath = value["xpath"]
            child_nodes = node.xpath(child_xpath)

            if debug:
                print(f"[DEBUG] Node<{rule_name}> child='{key}' xpath='{child_xpath}' -> {len(child_nodes)} matches")

            result[key] = [
                extract_node(child, key, config, debug) for child in child_nodes
            ]

        # Simple field (string rule)
        elif isinstance(value, str):
            vals = node.xpath(value)
            vals = [v if isinstance(v, str) else v.text for v in vals]

            if debug:
                if vals:
                    print(f"[DEBUG] Node<{rule_name}> field='{key}' xpath='{value}' -> {vals}")
                else:
                    print(f"[WARN] Node<{rule_name}> field='{key}' xpath='{value}' -> NO MATCH")

            result[key] = vals if len(vals) > 1 else (vals[0] if vals else None)

    return result


def parse_xml(xml_file: str, config: dict, debug: bool = False) -> dict:
    tree = etree.parse(xml_file)
    results = {}

    for node_type, rules in config["xpaths"].items():
        xpath_expr = rules.get("xpath")
        if not xpath_expr:
            continue

        nodes = tree.xpath(xpath_expr)

        if debug:
            print(f"[DEBUG] Root node_type='{node_type}' xpath='{xpath_expr}' -> {len(nodes)} matches")

        results[node_type] = [
            extract_node(node, node_type, config, debug) for node in nodes
        ]

    return results


def output_results(results: dict, config: dict):
    fmt = config["output"]["format"]
    if fmt == "terminal":
        print(json.dumps(results, indent=2))
    elif fmt == "json":
        out_file = config["output"]["file"]
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Results written to {out_file}")


def main():
    config = load_config("config.toml")
    xml_file = config["input"]["xml_file"]
    debug = config.get("debug", {}).get("enabled", False)

    results = parse_xml(xml_file, config, debug)
    output_results(results, config)


if __name__ == "__main__":
    main()

