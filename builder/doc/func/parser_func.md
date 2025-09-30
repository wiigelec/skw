# Functional Specification: `skw_parser.py`

The **SKWParser** module is a specialized component responsible for transforming a semi-structured XML source document (a "Book") into a fully structured, machine-readable JSON format. Its operation is guided entirely by a profile-specific `parser.toml` configuration file.

---

## Core Responsibilities 🎯

- **Configuration Loading**: Reads and interprets a `parser.toml` file to get all necessary paths, filters, and XPath expressions.  
- **XML Parsing**: Loads and traverses a source XML document using the `lxml` library.  
- **Data Extraction**: Systematically extracts build metadata and instructions for each relevant section of the Book.  
- **Dependency Resolution**: Constructs a dependency graph and resolves dependency cycles according to explicit configuration overrides.  
- **Custom Package Injection**: Augments the parsed data with additional build steps defined entirely in TOML configuration files.  
- **Structured Output**: Generates a single, correctly ordered, well-formed JSON file containing an array of all build entries.  

---

## Functional Requirements ✅

### Initialization and Configuration
The parser must be initialized with the context of a specific Book and Profile. Upon initialization, it must locate and load the corresponding `parser.toml` configuration file from the profile's directory. The system must exit with an error if the `parser.toml` file cannot be found.

### Primary XML Parsing Workflow
The system must identify and parse the source XML file whose path is specified in `parser.toml`. It must exit with an error if this file does not exist.  
The parser iterates through the XML document by first identifying **chapter** elements and then nested **section** elements, using XPath expressions provided in the configuration.  
It must support filtering to selectively include or exclude specific chapters and sections based on their ID attributes, as defined in the configuration.

### Data Extraction
For each valid section, the parser must extract the following data points using configured XPath expressions:

- **Package Metadata**: The package name and version.  
- **Source Information**: Lists of source file titles, download URLs, and checksums.  
- **Dependencies**: A list of required package dependencies.  
- **Build Instructions**: An ordered list of shell commands, extracted by finding specific nodes and concatenating their text content.  

### Hierarchical XPath Configuration
A key feature of the parser is its flexible, override-based configuration for XPath expressions.  
The system uses a hierarchical lookup (`_get_xpath_expr` method) to determine which XPath expression to use for a given data point. The order of precedence is:

1. An expression defined specifically for a **section ID**.  
2. An expression defined for the **parent chapter ID**.  
3. A global default expression in the main `[xpaths]` table.  

This allows the configuration to handle structural exceptions in the XML for specific sections without needing to change the global rules.

---

## Dependency Resolution and Build Order Generation ⛓️

After extracting all packages, the parser must build a dependency graph and generate a linear build sequence. The resolution of dependency cycles is handled entirely by user-provided configuration.

- **Graph Construction**: The parser must construct an internal directed graph. Each package represents a node, and each declared dependency creates a directed edge from a package to its dependency.  
- **Cycle Detection and Config-Driven Resolution**: The system must detect cycles within the dependency graph.  
  - When a cycle is detected, the parser will scan the `parser.toml` file for a configuration (e.g., an `[[ordered_build_groups]]` table) that provides a manual build order for all packages involved in that cycle.  
  - If a matching configuration is found, the parser will adopt the explicitly defined sequence for that group of packages, overriding the graph's cyclic nature for output generation.  
  - If a cycle is detected for which no manual ordering is defined in the configuration, it is considered a **fatal error**. The parser must report the unhandled circular dependency, list the packages involved, and terminate immediately with a non-zero exit code.  
- **Topological Sorting**: For all packages not part of a manually ordered group, a standard topological sort is performed. The final build list is constructed by integrating the sorted list of standard packages with the explicitly configured build groups at the correct positions.  

---

## Custom Package Injection

The parser must be able to inject build steps that are not present in the source XML document via `custom_packages` tables in TOML.  
This feature is the primary mechanism for defining the components needed to resolve circular dependencies (e.g., creating `gcc-pass1` and `gcc-final` as two distinct custom packages).  
The user is responsible for defining all necessary package variations and then orchestrating their build order using the manual configuration described above.

---

## Output Generation

After processing all packages and resolving the build order, the parser collects all build steps into a single list of dictionary objects.  
It must create the necessary output directory structure (`build/parser/<book>/<profile>/`) if it does not exist.  

The final list of entries written to the JSON file must represent the exact, linear build sequence determined by the dependency resolution logic, combining topologically sorted items and manually ordered groups. The output must use indentation for human readability.
