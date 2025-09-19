# Functional Specification: skw_scripter.py

> The **SKWScripter** module is the final stage in the build preparation process. It takes the structured JSON data produced by the **SKWParser**, applies a series of template expansions and transformations, and generates a set of ordered, executable shell scripts. Its behavior is controlled by a profile-specific `scripter.toml` configuration file.

---

## Core Responsibilities 🎯

* **Configuration Loading**: Reads and interprets a `scripter.toml` file to get templates, regex rules, and other settings.
* **Template Processing**: Selects and populates script templates with the structured data from the parser's JSON output.
* **Content Transformation**: Applies a series of configurable regular expression and literal string substitutions to the generated script content.
* **Script Generation**: Creates a sequence of named, ordered, and executable shell script files in the build directory.

---

## Functional Requirements ✅

### Initialization and Configuration

The scripter must be initialized with the context of a specific **Book** and **Profile**. Upon initialization, it must locate and load the corresponding `scripter.toml` configuration file. It also pre-loads a `default_template` file specified in the configuration. The system must exit with an error if either the configuration or the default template file is not found.

### Primary Scripting Workflow

The scripter's main `run` method must execute the following sequence for each entry in the input `parser_output.json` file:
1.  **Select a Template**: Choose the appropriate script template based on a hierarchical lookup.
2.  **Expand the Template**: Populate the template by replacing placeholders (e.g., `{{package_name}}`) with data from the JSON entry.
3.  **Apply Transformations**: Modify the resulting content by applying a series of configured regex and literal string substitutions.
4.  **Write the Script**: Save the final content to a uniquely named and ordered shell script file and set its permissions to be executable.

### Hierarchical Template Selection

The system must use a hierarchical lookup to determine which script template to use for a given build entry. The order of precedence is:
1.  A template defined for a specific **package name**.
2.  A template defined for a **section ID**.
3.  A template defined for a **chapter ID**.
4.  The **default template** specified in the main configuration.

If a specified template file is not found, the system will issue a warning and fall back to using the default template content.

### Template Expansion

The system must replace placeholders in the format `{{key.subkey}}` within the template content with corresponding values from the input JSON data.
* For simple string values, it performs a direct substitution.
* For lists of values, it joins them into a single string. Specifically, `build_instructions` are joined with newlines, while other lists are joined with spaces.
* If a key is not found in the data, it is replaced with an empty string.

### Regex and Literal Transformations

After template expansion, the system must apply a series of transformations defined in `scripter.toml`.
* These transformations can be defined globally or be specific to a package, section, or chapter.
* The system supports two modes for transformations, determined by the first character of the rule:
    * **Literal (`s`)**: A literal search-and-replace, following the format `s/find_string/replace_string/`. The system will escape the `find_string` to treat it as a plain string.
    * **Regex (`r`)**: A regular expression search-and-replace, following the format `r/regex_pattern/replacement/`. This mode supports capture groups in the replacement string.

### Output Generation

For each processed entry, the system must generate an executable shell script.
* The script's filename must be formatted to ensure sequential execution, using a zero-padded index, chapter ID, and section ID (e.g., `0001_chapter-intro_section-core.sh`).
* The generated script files must be written to the `build/scripter/<book>/<profile>/scripts/` directory.
* The file permissions must be set to `755` to make the script executable.
