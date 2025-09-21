# Configuration Reference: parser.toml

> The **`parser.toml`** file is the central configuration for the `SKWParser` module. It dictates how the parser should read a source XML "Book," extract the necessary build information, and handle exceptions. Its primary components include file paths, a comprehensive set of XPath expressions for data extraction, and filters to include or exclude specific parts of the book.

---

## `[main]` section

This section defines the core input and output files for the parser.

### **`xml_path`**

* **Type**: `String`
* **Description**: The path to the source XML "Book" file that the parser will process. This path can contain variables like `${book}` which will be substituted by the parser at runtime.
* **Example**: `xml_path = "build/books/${book}/lfs-full.xml"`

### **`output_file`**

* **Type**: `String`
* **Description**: The name of the JSON file that the parser will generate. This file will be placed in the `build/parser/<book>/<profile>/` directory.
* **Example**: `output_file = "parser_output.json"`

---

## `[xpaths]` section

This section contains the global default XPath expressions used to extract data from the XML document. These expressions can be overridden on a per-chapter or per-section basis.

* **`chapter_id`**: Identifies the main "chapter" elements in the XML.
* **`section_id`**: Identifies the "section" elements nested within a chapter.
* **`package_name`**, **`package_version`**: Extract the name and version of the software package being built in a given section.
* **`source_urls`**, **`source_checksums`**: Extract the download URLs for source tarballs or patches and their corresponding checksums. These expressions can use variables like `${package_name}` for dynamic path generation.
* **`build_instructions`**: The most critical expression, which locates the nodes containing the shell commands for building the package. The parser iterates over these nodes and concatenates their text content to form a list of commands.

---

## XPath Overrides

To handle structural inconsistencies in the source XML, you can override the global XPath expressions for specific chapters or sections. The parser uses a hierarchical lookup: **section-specific > chapter-specific > global default**.

* **Syntax**: `[<chapter_id>.xpaths]` or `[<section_id>.xpaths]`
* **Example**: The `[ch-materials-patches.xpaths]` table overrides the `source_urls` expression specifically for the section with `id="ch-materials-patches"` to look for `.patch` files instead of `.tar` files. Similarly, many sections like `ch-tools-creatingminlayout` override `source_urls` to be an empty string because they don't involve downloading any source code.

---

## Filters

Filters allow you to selectively process or ignore certain parts of the XML book.

### **`[chapter_filters]`** and **`[section_filters]`**

* **Type**: `Table` with `include` and `exclude` keys.
* **Description**: These tables contain lists of chapter or section IDs to either exclusively include or explicitly exclude from the parsing process. If the `include` list is not empty, only IDs in that list will be processed. The `exclude` list always takes precedence.
* **Example**: `exclude = [ "chapter-intro", "chapter-partitioning" ]` prevents introductory chapters that don't contain build steps from being processed.
