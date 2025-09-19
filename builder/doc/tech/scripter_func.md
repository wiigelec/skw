# Technical Specification: skw_scripter.py

> This document provides a detailed technical specification for the `SKWScripter` module. It is intended for developers who need to understand the internal workings, data structures, and algorithms of the script.

---

## 1. Overview 📜

The `SKWScripter` class is a template-based script generator. It consumes a structured JSON file (produced by `SKWParser`), processes each entry through a series of hierarchical template selections, placeholder expansions, and regex-based transformations. The final output is a directory of ordered, executable shell scripts. The entire process is configured via a profile-specific `scripter.toml` file.

---

## 2. Dependencies 📦

* **`tomllib`**: For parsing `.toml` configuration files.
* **Standard Libraries**: `os`, `sys`, `json`, `re`.

---

## 3. Class `SKWScripter`

### Class Overview

This is the sole class in the module. An instance of `SKWScripter` represents a single script generation job for a specific Book and Profile combination.

### Attributes

| Attribute          | Type   | Description                                                                 |
| ------------------ | ------ | --------------------------------------------------------------------------- |
| `build_dir`        | `str`  | The absolute path to the main build directory.                              |
| `profiles_dir`     | `str`  | The absolute path to the directory containing all book/profile configs.     |
| `book`             | `str`  | The name of the book being processed (e.g., "lfs").                         |
| `profile`          | `str`  | The name of the profile being used (e.g., "systemd").                       |
| `config_path`      | `str`  | The full path to the profile-specific `scripter.toml` file.                   |
| `cfg`              | `dict` | A dictionary containing the entire parsed `scripter.toml` configuration.      |
| `template_path`    | `str`  | The full path to the default template script file.                          |
| `default_template` | `str`  | The string content of the default template file, loaded at initialization.  |

### Methods

#### `__init__(self, build_dir, profiles_dir, book, profile)`

* **Purpose**: Initializes the scripter object by setting up paths and loading configuration and the default template.
* **Parameters**:
    * `build_dir` (`str`): The path to the build directory.
    * `profiles_dir` (`str`): The path to the profiles directory.
    * `book` (`str`): The name of the target book.
    * `profile` (`str`): The name of the target profile.
* **Logic**:
    1.  Stores the constructor arguments as instance attributes.
    2.  Constructs the path to `scripter.toml` and loads it into `self.cfg`. Exits if not found.
    3.  Retrieves the `default_template` filename from the loaded configuration.
    4.  Constructs the full path to the default template and reads its content into `self.default_template`. Exits if not found.

#### `run(self)`

* **Purpose**: The main execution method that drives the entire script generation process from JSON input to executable file output.
* **Algorithm**:
    1.  Defines the path to the input `parser_output.json` file.
    2.  Defines the output directory path for the generated scripts.
    3.  Verifies the input JSON file exists; exits with an error if not.
    4.  Creates the output script directory using `os.makedirs(..., exist_ok=True)`.
    5.  Loads the entire JSON array from the input file.
    6.  Iterates through each `entry` (a dictionary) in the JSON array using `enumerate` to track the index.
    7.  **For each entry, it performs the following steps**:
        a.  Calls `_select_template(entry)` to get the appropriate template content as a string.
        b.  Calls `_expand_template(entry, template_content)` to substitute placeholders in the template, producing the initial script content.
        c.  Calls `_apply_regex(entry, script_content)` to apply all relevant transformations to the script content.
        d.  Generates a zero-padded sequential filename (e.g., `0042_chapter-5_binutils.sh`).
        e.  Writes the final script content to the file in the output directory.
        f.  Makes the newly created script file executable by setting its permissions to `0o755`.

#### `_expand_template(self, entry, template_content)`

* **Purpose**: Replaces `{{...}}` placeholders in a template string with data from a given entry.
* **Parameters**:
    * `entry` (`dict`): The JSON object for a single build step.
    * `template_content` (`str`): The raw string content of the template to be populated.
* **Returns**: `str`. The template string with all placeholders substituted.
* **Logic**:
    1.  Uses `re.sub()` with a callback function to find all occurrences of `{{...}}`.
    2.  The callback function extracts the key inside the braces (e.g., `package_name` or `sources.urls`).
    3.  It traverses the `entry` dictionary to find the corresponding value.
    4.  **List Handling**: If the resolved value is a list, it is flattened into a string. A special case exists for the key `build_instructions`, which is joined by newlines (`\n`). All other lists are joined by spaces.
    5.  If a key is not found, it is replaced with an empty string.

#### `_apply_regex(self, entry, content)`

* **Purpose**: Applies a series of literal and regular expression transformations to the script content.
* **Parameters**:
    * `entry` (`dict`): The current build entry, used to determine which rules to apply.
    * `content` (`str`): The script content after template expansion.
* **Returns**: `str`. The script content after all transformations have been applied.
* **Logic**:
    1.  Aggregates a list of transformation rules from `self.cfg` based on a hierarchy: global rules are added first, followed by chapter-, section-, and package-specific rules.
    2.  Iterates through each transformation rule string.
    3.  Parses the rule to identify the mode (`s` for literal, `r` for regex), the delimiter, the search pattern, and the replacement string.
    4.  If the mode is `s`, it performs a literal search-and-replace using `re.sub()` with `re.escape()` on the search pattern.
    5.  If the mode is `r`, it performs a standard regular expression search-and-replace using `re.sub()`.
    6.  The process is wrapped in a `try...except` block to gracefully handle malformed regex patterns.

#### `_select_template(self, entry)`

* **Purpose**: Selects the appropriate template file to use for a given entry based on a hierarchical lookup.
* **Parameters**:
    * `entry` (`dict`): The current build entry.
* **Returns**: `str`. The string content of the selected template file.
* **Logic**: It determines the template filename to use with the following order of precedence:
    1.  **Package-specific**: Checks for a `template` key in `self.cfg` under the entry's `package_name`.
    2.  **Section-specific**: If no package-specific template is found, checks under the entry's `section_id`.
    3.  **Chapter-specific**: If none of the above are found, checks under the entry's `chapter_id`.
    4.  **Default**: If no specific template is found, it uses the default template filename.
* If the selected template file exists, its content is read and returned. Otherwise, a warning is printed and the pre-loaded `self.default_template` content is returned.

---

## 4. Configuration (`scripter.toml`) ⚙️

The script's behavior is controlled by the `scripter.toml` file, which is expected to have the following structure:

```toml
# Main configuration block
[main]
default_template = "template.script" # Specifies the fallback template

# Global transformations applied to all scripts
[global.regex]
patterns = [
  's/old_literal_string/new_string/',
  'r/some_regex(.*)/replacement \\1/'
]

# Chapter-specific overrides
[chapter-5]
template = "custom-chapter5-template.script" # Override template for this chapter

[chapter-5.regex]
patterns = [ 's/specific-to-ch5/replacement/' ]

# Section-, and Package-specific overrides follow the same pattern
# [binutils]
# template = "binutils.script"
