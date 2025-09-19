# Functional Specification: skw_parser.py

> The **SKWParser** module is a specialized component responsible for transforming a semi-structured XML source document (a "Book") into a fully structured, machine-readable JSON format. Its operation is guided entirely by a profile-specific `parser.toml` configuration file.

---

## Core Responsibilities 🎯

* **Configuration Loading**: Reads and interprets a `parser.toml` file to get all necessary paths, filters, and XPath expressions.
* **XML Parsing**: Loads and traverses a source XML document using the `lxml` library.
* **Data Extraction**: Systematically extracts build metadata and instructions for each relevant section of the Book.
* **Custom Package Injection**: Augments the parsed data with additional build steps defined entirely in TOML configuration files.
* **Structured Output**: Generates a single, well-formed JSON file containing an array of all extracted build entries.

---

## Functional Requirements ✅

### Initialization and Configuration

The parser must be initialized with the context of a specific **Book** and **Profile**. Upon initialization, it must locate and load the corresponding `parser.toml` configuration file from the profile's directory. The system must exit with an error if the `parser.toml` file cannot be found.

### Primary XML Parsing Workflow

The system must identify and parse the source XML file whose path is specified in `parser.toml`. It must exit with an error if this file does not exist. The parser iterates through the XML document by first identifying "chapter" elements and then nested "section" elements, using XPath expressions provided in the configuration. It must support **filtering** to selectively include or exclude specific chapters and sections based on their ID attributes, as defined in the configuration.

### Data Extraction

For each valid section, the parser must extract the following data points using configured XPath expressions:
* **Package Metadata**: The package name and version.
* **Source Information**: Lists of source file titles, download URLs, and checksums.
* **Dependencies**: A list of required dependencies.
* **Build Instructions**: An ordered list of shell commands, extracted by finding specific nodes and concatenating their text content.

### Hierarchical XPath Configuration

A key feature of the parser is its flexible, override-based configuration for XPath expressions. The system uses a hierarchical lookup (the `_get_xpath_expr` method) to determine which XPath expression to use for a given data point. The order of precedence is:

1.  An expression defined specifically for a **section ID**.
2.  An expression defined for the parent **chapter ID**.
3.  A global default expression in the main `[xpaths]` table.

This allows the configuration to handle structural exceptions in the XML for specific sections without needing to change the global rules.

### Custom Package Injection

The parser must be able to inject build steps that are not present in the source XML document. The system looks for a list of custom configuration files defined in `parser.toml`. For each file, it processes a list of `custom_packages`. Build instructions for these packages can be defined in two ways:

1.  As a list of inline string `commands` in the TOML file.
2.  As a list of `xpath_commands` that extract commands from the main source XML document.

### Output Generation

After processing all sections and custom packages, the parser collects all extracted data into a single list of dictionary objects. It must create the necessary output directory structure (`build/parser/<book>/<profile>/`) if it does not exist. The system writes the final list of data to a JSON file in the output directory, using indentation for human readability.
