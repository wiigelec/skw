# ScratchKit Builder (SKW Buider)

ScratchKit Builder is a sophisticated, automated build system designed to construct custom Linux distributions from source. It is heavily inspired by projects like Linux From Scratch (LFS) and automates the entire pipeline, from parsing build instructions to compiling, packaging, and deploying the resulting software.

## Core Responsibilities 🎯

The system is broken down into three primary stages:

1.  **Parser (`skw_parser.py`)**: Transforms a semi-structured XML source document (a "Book") into a fully structured, machine-readable JSON format. Its behavior is guided by a profile-specific `parser.toml` configuration file.
2.  **Scripter (`skw_scripter.py`)**: Takes the structured JSON data from the Parser and generates a set of ordered, executable shell scripts. This stage uses script templates and applies a series of configurable regular expression and literal string substitutions.
3.  **Executer (`skw_executer.py`)**: The execution engine that runs the generated scripts in the correct environment. It manages the build lifecycle, including caching, package creation, integrity verification, and deployment.

---

## Key Features ✅

* **Configuration-Driven**: Every stage of the build process is controlled by `.toml` configuration files, allowing for highly flexible and customizable build profiles.
* **Hierarchical Configuration**: Utilizes an override-based system for configurations (e.g., XPath expressions, templates, regex rules), allowing for global, chapter-specific, section-specific, or even package-specific rules.
* **Tiered Caching**: Supports checking multiple local and remote repositories for pre-built packages to avoid redundant compilation, significantly speeding up builds.
* **Package Integrity**: Ensures the integrity of all downloaded packages by verifying SHA256 checksums against stored metadata before installation.
* **Environment Management**: Intelligently determines whether each script should run on the host system or within an isolated `chroot` environment based on configuration rules.
* **Context-Aware Packaging**: Generates uniquely named package archives based on a configurable template, preventing collisions between different build stages (e.g., cross-tools vs. final system).
* **Rich Metadata**: Creates detailed `.meta.json` files for each package, capturing build context, timestamps, file manifests, and checksums.

---

## Workflow

The end-to-end workflow is managed by the main `builder.py` script.

1.  **Setup**: A user defines a "Book" (e.g., LFS) and a "Profile" (e.g., systemd). This creates a directory structure with skeleton configuration files (`book.toml`, `parser.toml`, `scripter.toml`, `executer.toml`).
2.  **Installation**: The source XML for the Book is downloaded and prepared using the `install-book` command.
3.  **Parse**: The `parse` command is run, which executes the `SKWParser` to generate `parser_output.json`.
4.  **Script**: The `script` command is run, which executes the `SKWScripter` to generate executable build scripts based on the JSON data.
5.  **Execute**: The `execute` command is run, which starts the `SKWExecuter`. It iterates through the scripts, checks for cached packages, and runs the build, package, and deploy lifecycle for each one.

---

## Usage

The primary interface is the `skw-build` command-line tool.

```bash
# List available books
./skw-build list-books

# Add a new book
./skw-build add-book --name <book_name>

# Add a new profile to a book
./skw-build add-profile --book <book_name> --name <profile_name>

# Install the book sources
./skw-build install-book --book <book_name>

# Run the full pipeline
./skw-build parse --book <book_name> --profile <profile_name>
./skw-build script --book <book_name> --profile <profile_name>
./skw-build execute --book <book_name> --profile <profile_name> --yes
