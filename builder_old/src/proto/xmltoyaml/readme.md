# Functional & Technical Specification  
## TomlXmlToYamlConverter

This document specifies the functionality, architecture, and implementation details of the **TomlXmlToYamlConverter** Python script (`xmltoyaml.py`). The tool extracts structured data from an XML file based on a TOML-defined mapping and outputs the results into multiple ordered YAML files.

---

# 1. Overview and Purpose

The **TomlXmlToYamlConverter** converts arbitrary XML data into structured YAML files.  
The structure and extraction logic are defined entirely within a **TOML configuration file**.

The core purpose is to:

- Read a TOML configuration, preserving key order.
- Read an input XML document.
- Iterate over matches of the first TOML section's XPath to generate one YAML file per match.
- Use TOML keys to define YAML structure and TOML values to define XPath extraction logic.
- Support cross-section data referencing via `{field}` placeholders in XPath.
- Output human-readable YAML with preserved order and literal (`|`) blocks for multiline text.

---

# 2. Architecture and Data Flow

The system is implemented as a single Python class: **`TomlXmlToYamlConverter`**.

| Step | Component | Input | Output | Description |
|------|-----------|--------|---------|-------------|
| 1 | `_load_toml` | TOML file | `self.toml_data` (OrderedDict) | Loads mapping, preserving order. |
| 2 | `_load_xml` | XML file | `self.xml_tree` | Loads XML with blank text removed. |
| 3 | `_resolve_section` (Top-Level) | TOML + XML | List of OrderedDict entries | Iterates over nodes matching first section's XPath. |
| 4 | `_resolve_section` (Recursive) | Section + XML Node + Context | Single OrderedDict | Extracts fields and nested sections recursively. |
| 5 | `_extract_value` | XML Node + XPath + Context | String or List | Executes XPath and normalizes results. |
| 6 | `_generate_yaml_files` | List of entries | YAML files | Generates filenames + writes each file. |
| 7 | `_write_yaml` | Entry + Path | YAML file | Pretty-printed YAML with preserved order. |

---

# 3. Core Functionality Specification

## 3.1 TOML Mapping Structure

The TOML file defines hierarchy and extraction rules.

### Sections
Each `[section]` maps to a corresponding dictionary/object in YAML.

### `xpath = "..."`  
For the **first** section:
- Determines the iteration nodes for output files.

For nested sections:
- XPath is conceptually relative to the parent node, but currently evaluated globally unless `{field}` placeholders introduce locality.

### Value Keys
`key = "XPath"` → Extracts a value into YAML via XPath.

### Child Keys
`childN = [ "sectionA", "sectionB", ... ]`  
Declares nested sections, preserving order.

---

## 3.2 Data Extraction (`_extract_value`)

**Context Substitution**
- `{field}` placeholders are replaced with values from `local_context`.
- Values are escaped for XPath safety (`'` → `&apos;`).

**XPath Execution**
- Runs on the provided XML node.

**Result Handling**
- Element → stripped text.
- String/Int/Float → string value.
- Multiple results → list.
- Lists of single characters → collapsed to a single string.
- Empty results → empty string.

---

## 3.3 Recursive Resolution (`_resolve_section`)

**Order Preservation**
- Uses TOML load order (OrderedDict).

**Context Flow**
- Extracted values immediately added to `local_context`.

**Top-Level Operation**
- If `context_node is None` and section is first:
  - Execute its XPath to get nodes.
  - Return a list of resolved entries.

**Nested Sections**
- For each `childN` key:
  - Recursively resolve listed child sections using the same XML node.

---

## 3.4 Output Generation & Filename (`_generate_yaml_files`)

A YAML file is produced for each top-level entry.

**Filename Logic**
- Derived from the **first two keys** in the resolved entry.
- Example: `bash-5.2.yaml`.

**Sanitization**
- Any character not `[A-Za-z0-9._-]` → `_`.

**Fallback**
- If fewer than two keys exist → `entry.yaml`.

---

## 3.5 Pretty YAML Writer (`_write_yaml`)

- Key order preserved (`sort_keys=False`).
- Strings with newlines use literal block (`|`).
- Writer formatting:
  - `indent = 2`
  - `default_flow_style = False`
  - `width = 1000`

---

# 4. Dependencies

| Library | Purpose |
|---------|---------|
| `toml` | Load TOML as OrderedDict |
| `yaml` | Write YAML with custom representers |
| `lxml.etree` | XML parsing + XPath |
| `argparse` | CLI handling |
| `pathlib.Path` | Filesystem handling |
| `collections.OrderedDict` | Order preservation |

---

# 5. Command-Line Interface

```
python3 xmltoyaml.py <xml_path> <toml_path> <output_dir>
```

| Argument | Description | Example |
|----------|-------------|----------|
| `xml_path` | Input XML file | `book.xml` |
| `toml_path` | TOML mapping file | `config.toml` |
| `output_dir` | Directory for YAML output | `output/packages` |

