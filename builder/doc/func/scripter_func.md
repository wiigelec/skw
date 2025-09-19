This document is a functional specification for the skw_parser.py script, a specialized module within the ScratchKit Builder system.

1. Overview 🧩
The SKWParser is responsible for transforming a semi-structured XML source document (a "Book") into a fully structured, machine-readable format. Guided by a profile-specific parser.toml configuration file, it uses XPath expressions to locate and extract key build information, such as package names, source URLs, and command sequences. The final output is a standardized JSON file that serves as the input for the next stage in the toolchain, the Scripter.

2. Core Responsibilities 🎯
Configuration Loading: Read and interpret a parser.toml file to get all necessary paths, filters, and XPath expressions.

XML Parsing: Load and traverse a source XML document using the lxml library.

Data Extraction: Systematically extract build metadata and instructions for each relevant section of the Book.

Custom Package Injection: Augment the parsed data with additional build steps defined entirely in TOML configuration files.

Structured Output: Generate a single, well-formed JSON file containing an array of all extracted build entries.

3. Functional Requirements ✅
Initialization & Configuration
The parser must be initialized with the context of a specific Book and Profile. Upon initialization, it must locate and load the corresponding parser.toml configuration file from the profile's directory. The system must exit with an error if the parser.toml file cannot be found.

Primary XML Parsing Workflow
The system must identify and parse the source XML file whose path is specified in parser.toml. It must exit with an error if this file does not exist. The parser must iterate through the XML document by first identifying "chapter" elements and then nested "section" elements, using XPath expressions provided in the configuration. It must support filtering to selectively include or exclude specific chapters and sections based on their ID attributes.

Data Extraction
For each valid section, the parser must extract the following data points:

Package Metadata: The package name and version.

Source Information: Lists of source file titles, download URLs, and checksums.

Dependencies: A list of required dependencies.

Build Instructions: An ordered list of shell commands, extracted by finding specific nodes and concatenating their text content.

Hierarchical XPath Configuration
A key feature of the parser is its flexible, override-based configuration for XPath expressions. The system must use a hierarchical lookup to determine which XPath expression to use for a given data point. The order of precedence must be:

An expression defined specifically for a section ID.

An expression defined for a chapter ID.

A global default expression in the main [xpaths] table.

This allows the configuration to handle structural exceptions in the XML for specific sections without needing to change the global rules.

Custom Package Injection
The parser must be able to inject build steps that are not present in the source XML. The system must look for a list of custom configuration files defined in parser.toml. For each file, it must process a list of custom_packages. For each custom package, it must assemble a build entry using metadata defined directly in the TOML file (name, version, etc.).

Build instructions for these packages can be defined in two ways:

As a list of inline string commands in the TOML file.

As a list of XPath expressions that extract commands from the main source XML document.

Output Generation
After processing all sections and custom packages, the parser must collect all extracted data into a single list of dictionary objects. It must create the necessary output directory structure (build/parser/<book>/<profile>/) if it does not exist. The system must write the final list of data to a JSON file in the output directory, using indentation for human readability.
