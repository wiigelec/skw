# Functional & Technical Specification: **TomlXmlToYamlConverter**

This document specifies the functionality, architecture, and implementation details of the **TomlXmlToYamlConverter** Python script (`xmltoyaml.py`), which extracts structured data from an XML file based on a TOML-defined mapping and outputs multiple, ordered YAML files.

---

## 1. Overview and Purpose

The **TomlXmlToYamlConverter** converts arbitrary XML data into structured YAML files.  
The structure and content extraction logic are defined entirely within a TOML configuration file.

### Core Objectives
- Read a TOML configuration, preserving key order.
- Read an input XML document.
- Iterate over matches of the first TOML section’s XPath to generate multiple output YAML files.
- Use TOML keys to define output YAML structure and values to define XPath extraction logic.
- Support cross-section data referencing via `{field}` placeholders in XPaths.
- Ensure YAML outputs are human-readable, preserving TOML order and formatting multiline strings with literal (`|`) blocks.

---

## 2. Architecture and Data Flow

| Step | Component | Input | Output | Description |
|------|------------|--------|---------|-------------|
| 1 | `_load_toml` | TOML File | OrderedDict | Loads the mapping, preserving order. |
| 2 | `_load_xml` | XML File | lxml tree | Loads and parses XML. |
| 3 | `_resolve_section` | TOML + XML | OrderedDict | Resolves sections recursively. |
| 4 | `_write_yaml` | Data | YAML File | Outputs formatted YAML. |

---

## 3. Command-Line Interface

```bash
python3 xmltoyaml.py <xml_path> <toml_path> <output_dir>
```

Example:
```bash
python3 xmltoyaml.py book.xml xmltoyaml.toml ./output/
```
