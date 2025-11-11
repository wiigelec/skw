# Specification: TomlToYamlXPathConverter

## 1. Overview

The **TomlToYamlXPathConverter** class converts a TOML configuration file into a structured YAML document.  
The process is driven by an input JSON list of package identifiers, which are used to execute XPath expressions against a source XML file to extract package-specific metadata.

### Workflow
1. Read a JSON file containing a list of packages (name and version).
2. For each package, find the corresponding node(s) in the XML document based on the package name and version.
3. Execute the XPaths defined in the TOML file relative to that node, extracting metadata.
4. Output a YAML list where each item corresponds to a matched package.

---

## 2. Dependencies & Prerequisites

| Dependency | Purpose |
|-------------|----------|
| **toml** | Loading and parsing the input TOML file. |
| **PyYAML** | Writing the final output in YAML format. |
| **lxml** | Parsing XML and executing XPath queries. |
| **Standard Libraries** | json, argparse, pathlib, collections.OrderedDict |

---

## 3. Class Signature

**Class Name:** `TomlToYamlXPathConverter`

**Constructor:**

```python
def __init__(self, input_toml_path: str, output_yaml_path: str, xml_path: str, input_json_path: str):
```

**Key Properties:**

| Property | Type | Description |
|-----------|------|-------------|
| `self.input_toml_path` | Path | Path to the TOML configuration file. |
| `self.output_yaml_path` | Path | Output YAML file path. |
| `self.xml_root` | etree._Element (optional) | Root of the parsed XML document. |
| `self.toml_data` | OrderedDict | Parsed TOML configuration. |
| `self.input_json_path` | Path | Path to JSON file containing package list. |
| `self.package_list` | List[Dict[str, str]] | List of packages from JSON. |

The constructor must call `_load_xml()` and `_load_package_list()` during initialization.

---

## 4. Detailed Method Specifications

### 4.1 Data Loading

#### `_load_toml(self)`
Loads the TOML file into `self.toml_data` using `OrderedDict` to preserve key sequence.

#### `_load_xml(self, xml_path: Path)`
Parses the XML file using `lxml.etree.parse()`.  
Stores the root element in `self.xml_root`.

#### `_load_package_list(self, json_path: Path)`
Loads the JSON file containing a list of dictionaries with keys `"name"` and `"version"`.  
Stores the list in `self.package_list`.

---

### 4.2 Extraction Logic

#### `_find_xml_package_node(self, package_name: str, package_version: str) -> Optional[etree._Element]`
Searches `self.xml_root` to find the specific XML node that matches the given package name and version.  
Returns the first matching XML element or `None`.

#### `_execute_xpath(self, node: etree._Element, xpath_expression: str) -> str`
Executes the XPath expression relative to the provided node using `node.xpath()`.  
Returns the resulting string value.

---

### 4.3 Structure Building

#### `_resolve_children(self, node: OrderedDict, xml_context_node: etree._Element) -> OrderedDict`
Recursively processes a TOML table template.

- **Child Resolution:** Resolves and embeds tables referenced by child arrays.
- **Value Assignment:** If a value is a string, treat it as an XPath and resolve via `_execute_xpath()`.

#### `_build_structure(self) -> List[OrderedDict]`
1. Iterates over `self.package_list`.
2. Finds XML context node via `_find_xml_package_node()`.
3. If found, uses the root TOML table as a template and calls `_resolve_children()`.
4. Aggregates results into a list of structured dictionaries.

#### `_is_child(self, section_name: str) -> bool`
Helper function identifying sections that should only appear nested.

---

### 4.4 Output

#### `_write_yaml(self, data: List[OrderedDict])`
Writes the final structured data to the output YAML file.  
Uses `yaml.dump(data, indent=2, sort_keys=False)` to preserve key order.

---

## Example Usage

```python
converter = TomlToYamlXPathConverter(
    input_toml_path="config.toml",
    output_yaml_path="output.yaml",
    xml_path="packages.xml",
    input_json_path="packages.json"
)
data = converter._build_structure()
converter._write_yaml(data)
```
