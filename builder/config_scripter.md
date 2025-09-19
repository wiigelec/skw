# Configuration Reference: Scripter

> The **`scripter.toml`** file and its associated **`.script` templates** control the behavior of the `SKWScripter` module. This stage is responsible for transforming the structured JSON data from the parser into a series of executable shell scripts. The configuration defines which templates to use, how to populate them, and what transformations to apply to their content.

---

## `scripter.toml` Configuration

### `[main]` section

This section defines the global defaults for the scripter.

* **`default_template`**:
    * **Type**: `String`
    * **Description**: Specifies the filename of the default script template to use when no specific template is found for a given package, section, or chapter.
    * **Example**: `default_template = "template.script"`

### Template and Regex Overrides

The core of the scripter's flexibility comes from its hierarchical override system. You can define specific templates and regex transformations for packages, sections, or chapters. The lookup order of precedence is: **package > section > chapter > global**.

* **Syntax**:
    * `[<package_name>]`
    * `[<section_id>]`
    * `[<chapter_id>]`
    * `[global]`
* **Keys**:
    * `template = <filename>`: Overrides the script template for that context.
    * `regex = [ <rules> ]`: A list of regex/literal transformation rules to apply.
* **Example**:
    * The `[chapter-building-system]` table specifies that all build entries in that chapter should use the `chapter-building-system.script` template.
    * The `[ch-system-stripping]` section uses the `chroot-nosrc.script` template because it has no source code to extract.

### Regex Transformation Rules

The `regex` key contains a list of string patterns for transforming the generated script content. The scripter supports two modes:

1.  **Literal (`s`)**: Performs a literal string search-and-replace.
    * **Format**: `s@find_string@replace_string@` (the delimiter can be any character).
    * **Example**: `s@make check@#make check@` comments out the `make check` command.
2.  **Regex (`r`)**: Performs a regular expression search-and-replace, supporting capture groups.
    * **Format**: `r@regex_pattern@replacement@`
    * **Example**: `r@make(?: (.*))? install@make DESTDIR=$DESTDIR \\g<1> install@` intercepts all `make install` commands (with or without options) and prepends `make DESTDIR=$DESTDIR` to them, preserving any options.

---

## Script Templates (`.script` files)

Templates are shell script skeletons containing placeholders that are populated with data from `parser_output.json`.

### Placeholder Syntax

Placeholders use double curly braces, such as `{{key}}` or `{{key.subkey}}`. The scripter replaces these with the corresponding values from the JSON entry for each build step.

* **`{{package_name}}`**: The name of the package.
* **`{{package_version}}`**: The version of the package.
* **`{{sources.urls}}`**: A space-separated list of source code URLs.
* **`{{build_instructions}}`**: The list of build commands, joined by newlines to form the body of the script.

### Common Templates

* **`template.script`**: A generic, default template that extracts a source tarball and then runs the build instructions.
* **`chapter-building-system.script`**: A template for building the final system. It includes logic to set up a `DESTDIR` environment variable, which is crucial for installing software into a staging directory instead of the live system root.
* **`chapter-temp-tools.script`**: Used for building cross-compilation tools. It includes checks to ensure the `LFS` environment variable is set and that the script is running as the correct `lfs` user.
* **`write-config.script`**: A template used for steps that involve writing configuration files rather than compiling code. It does not include logic for extracting source tarballs.
* **`chroot-nosrc.script`**: A minimal template for commands that run inside the `chroot` environment and do not have any source code to download or extract.
