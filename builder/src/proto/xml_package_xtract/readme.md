# XMLPackageExtractor Class Specification

This specification defines the **XMLPackageExtractor** Python class.  
The class reads configuration from a TOML file, parses an XML document based on configurable XPath expressions, and outputs structured package data to a JSON file.

---

## 1. Dependencies and Requirements

**Purpose:** XML Parsing  
**Library:** `xml.etree.ElementTree` (standard library)  

**Purpose:** JSON Handling  
**Library:** `json` (standard library)  

**Purpose:** TOML Configuration  
**Library:** `tomli` (external) — required for reading TOML configuration files.

---

## 2. Configuration File (`config.toml`) Structure

The configuration file defines all extraction parameters and identifiers.

```toml
[book]
id = "lfs"  # A project or book identifier

[package]
node_xpath = "//packages/package"  # XPath to select parent nodes representing packages.
name_xpath = "./@name"             # Relative XPath to extract the package name.
version_xpath = "./version"        # Relative XPath to extract the package version.
```

---

## 3. Class Definition: `XMLPackageExtractor`

### Constructor (`__init__`)

**Signature:**
```python
__init__(self, xml_file_path: str, output_json_path: str, config_file_path: str)
```

**Parameters:**
- `xml_file_path`: Path to the input XML “book” file.  
- `output_json_path`: Path where the resulting JSON file will be saved.  
- `config_file_path`: Path to the TOML configuration file.  

**Behavior:**
- Stores file paths as instance attributes.  
- Immediately loads and validates all configuration values by calling `_load_config(config_file_path)`.

---

### Core Method: `extract_and_save`

**Signature:**
```python
extract_and_save(self)
```

**Behavior:**
1. Loads and parses the XML file using `_load_xml()`.  
2. Finds all package nodes using the configured `package.node_xpath`.  
3. Iterates through each package node:
   - Extracts `name` and `version` using `_extract_value()`.
   - Handles missing or malformed fields by logging and substituting `"N/A"`.
4. Constructs a structured output dictionary:

```json
{
  "book_id": "lfs",
  "packages": [
    {"name": "...", "version": "..."},
    ...
  ]
}
```

5. Saves the resulting data structure as a JSON file to `output_json_path`.

---

## 4. Helper Methods (Internal)

### `_load_config(config_file_path: str)`
- Reads and validates the TOML configuration.  
- Ensures required keys exist:
  - `book.id`
  - `package.node_xpath`
  - `package.name_xpath`
  - `package.version_xpath`
- Raises `KeyError` for missing keys or sections.

---

### `_load_xml()`
- Reads and parses the XML file using `ElementTree`.  
- Returns the root element of the XML tree.  
- Handles:
  - `FileNotFoundError` if the file is missing.  
  - `xml.etree.ElementTree.ParseError` if the XML is malformed.  

---

### `_extract_value(element, xpath: str)`
- Extracts a string value from a given XML element.  
- Handles both:
  - Attribute lookups (`./@name`)
  - Element text lookups (`./version`)
- Returns the string value or `None` if not found.

---

## 5. Output Specification

The output JSON file must contain two top-level keys:
- **book_id** (`string`): Identifier for the current book/project (from TOML `[book].id`).  
- **packages** (`list`): A list of package objects, each with `name` and `version` fields.

**Example output:**
```json
{
  "book_id": "lfs",
  "packages": [
    {"name": "zlib", "version": "1.3"},
    {"name": "bash", "version": "5.2"}
  ]
}
```

---

## 6. Error Handling

- **FileNotFoundError** — Raised when the XML or TOML file is missing.  
- **KeyError** — Raised when required keys or sections are missing in the TOML.  
- **ValueError** — Raised when XML or TOML syntax is invalid.  
- **Exception** — Used as a catch-all for unexpected runtime issues.

---

## 7. Summary

The **XMLPackageExtractor** class provides a configurable, robust, and modular way to extract structured data from XML files and output it in a machine-readable JSON format.  
It is suitable for automating build systems, documentation extractors, or data synchronization tools that rely on version-controlled XML sources.
