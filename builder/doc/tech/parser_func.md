# Technical Specification: skw_parser.py

> This document provides a detailed technical specification for the `SKWParser` module. It is intended for developers who need to understand the internal workings, data structures, and algorithms of the script.

---

## 1. Overview 📜

The `SKWParser` class is a configurable, XPath-driven parser designed to extract structured build information from an XML source file. It operates in two main phases: first, it parses the primary XML document based on hierarchical XPath rules; second, it injects additional build steps defined in separate TOML configuration files. The final output is a standardized JSON array of build entries.

---

## 2. Dependencies 📦

* **`lxml`**: For high-performance XML parsing and XPath evaluation.
* **`tomllib`**: For parsing `.toml` configuration files.
* **Standard Libraries**: `os`, `sys`, `json`.

---

## 3. Class `SKWParser`

### Class Overview

This is the sole class in the module. An instance of `SKWParser` represents a single parsing job for a specific Book and Profile combination.

### Attributes

| Attribute        | Type         | Description                                                                 |
| ---------------- | ------------ | --------------------------------------------------------------------------- |
| `build_dir`      | `str`        | The absolute path to the main build directory.                              |
| `profiles_dir`   | `str`        | The absolute path to the directory containing all book/profile configs.     |
| `book`           | `str`        | The name of the book being processed (e.g., "lfs").                         |
| `profile`        | `str`        | The name of the profile being used (e.g., "systemd").                       |
| `config_path`    | `str`        | The full path to the profile-specific `parser.toml` file.                   |
| `cfg`            | `dict`       | A dictionary containing the entire parsed `parser.toml` configuration.      |

### Methods

#### `__init__(self, build_dir, profiles_dir, book, profile)`

* **Purpose**: Initializes the parser object by setting up paths and loading the necessary configuration.
* **Parameters**:
    * `build_dir` (`str`): The path to the build directory.
    * `profiles_dir` (`str`): The path to the profiles directory.
    * `book` (`str`): The name of the target book.
    * `profile` (`str`): The name of the target profile.
* **Logic**:
    1.  Stores the constructor arguments as instance attributes.
    2.  Constructs the full path to `parser.toml` within the specified book and profile directory.
    3.  Checks if the file exists; if not, exits with an error.
    4.  Opens and parses the `parser.toml` file using `tomllib.load()` and stores the resulting dictionary in `self.cfg`.

#### `run(self)`

* **Purpose**: The main execution method that orchestrates the entire parsing and output generation process.
* **Algorithm**:
    1.  Retrieves the `xml_path` and `output_file` from `self.cfg['main']`, substituting variables using the `_substitute` helper.
    2.  Verifies the existence of the `xml_path`; exits with an error if not found.
    3.  Parses the XML file into an `lxml.etree` object.
    4.  Initializes an empty list named `results` to store all final build entries.
    5.  **Normal Parsing Phase**:
        * Retrieves chapter and section XPaths from the configuration.
        * Iterates through each "chapter" element found in the XML tree.
        * For each chapter, its ID is checked against include/exclude filters via `_filter_ok`.
        * Within each valid chapter, it iterates through each "section" element.
        * For each section, its ID is also checked against filters.
        * For each valid section, it constructs an `entry` dictionary by extracting data (`package_name`, `package_version`, `sources`, `dependencies`, `build_instructions`) using XPath expressions retrieved via the `_get_xpath_expr` hierarchical lookup method.
        * Appends the completed `entry` dictionary to the `results` list.
    6.  **Custom Code Injection Phase**:
        * Retrieves a list of custom configuration file paths from `self.cfg`.
        * Iterates through each custom config file.
        * Loads the custom TOML file.
        * For each package defined under the `custom_packages` key, it constructs an `entry` dictionary.
        * Build instructions are aggregated from two sources: an inline `commands` list and by executing `xpath_commands` against the main XML tree.
        * Appends the completed `entry` dictionary to the `results` list.
    7.  **Output Phase**:
        * Constructs the full output path for the JSON file.
        * Ensures the output directory exists using `os.makedirs(..., exist_ok=True)`.
        * Writes the `results` list to the output file as a formatted JSON string using `json.dump`.

#### `_get_xpath_expr(self, sec_id, chap_id, key)`

* **Purpose**: Implements the hierarchical lookup for an XPath expression.
* **Parameters**:
    * `sec_id` (`str`): The ID of the current section.
    * `chap_id` (`str`): The ID of the current chapter.
    * `key` (`str`): The key for the desired XPath (e.g., "package_name").
* **Returns**: `str` or `None`. The specific XPath expression string if found, otherwise `None`.
* **Logic**: It checks for the `key` in the configuration (`self.cfg`) in the following order of precedence:
    1.  Section-specific: `self.cfg[sec_id]['xpaths'][key]`
    2.  Chapter-specific: `self.cfg[chap_id]['xpaths'][key]`
    3.  Global: `self.cfg['xpaths'][key]`

#### `_expand_xpath(self, expr, context)`

* **Purpose**: Substitutes dynamic variables (e.g., `${package_name}`) into an XPath expression string.
* **Parameters**:
    * `expr` (`str`): The XPath expression string containing placeholders.
    * `context` (`dict`): A dictionary of keys and values to substitute.
* **Returns**: `str` or `None`. The expanded XPath string.

#### `_filter_ok(self, value, filters)`

* **Purpose**: Determines if a given ID should be processed based on include/exclude rules.
* **Parameters**:
    * `value` (`str`): The ID of the chapter or section to check.
    * `filters` (`dict`): A dictionary containing `include` and/or `exclude` lists.
* **Returns**: `bool`. `True` if the value passes the filter, `False` otherwise.

#### `_xpath_or_none(self, node, expr)`

* **Purpose**: Safely executes an XPath expression that is expected to return a single string result.
* **Parameters**:
    * `node` (`lxml.etree.Element`): The XML node to run the expression against.
    * `expr` (`str`): The XPath expression to execute.
* **Returns**: `str` or `None`. The string content of the first result, or `None` if the expression yields no results.

#### `_substitute(self, value)`

* **Purpose**: Performs simple, global substitutions in a string (e.g., `${book}`).
* **Parameters**:
    * `value` (`str`): The input string.
* **Returns**: `str`. The string with substitutions performed.

---

## 4. Data Structures 📊

### Output JSON Schema

The script's primary output is a JSON file containing a single array of "entry" objects. Each object represents a discrete build step and adheres to the following structure:

```json
[
  {
    "source_book": "str",
    "chapter_id": "str",
    "section_id": "str",
    "package_name": "str",
    "package_version": "str",
    "sources": {
      "titles": ["str"],
      "urls": ["str"],
      "checksums": ["str"]
    },
    "dependencies": ["str"],
    "build_instructions": ["str"]
  }
]
