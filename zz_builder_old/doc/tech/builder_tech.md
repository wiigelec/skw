# Technical Specification: builder.py

> This document provides a detailed technical specification for the **`builder.py`** script, the main entry point and command-line orchestrator for the ScratchKit (SKW) build system. It is intended for developers who need to understand its internal workings, class structure, and command-line interface.

---

## 1. Overview 📜

The `builder.py` script serves as the central controller for the entire ScratchKit build pipeline. It parses command-line arguments to drive the system's functionality, including project scaffolding (adding books and profiles), managing build sources, and invoking the three core modules in sequence: `SKWParser`, `SKWScripter`, and `SKWExecuter`. Its operation is configured by a top-level `builder.toml` file.

---

## 2. Dependencies 📦

* **Standard Libraries**: `os`, `sys`, `glob`, `tomllib`, `argparse`, `shutil`, `subprocess`.
* **Internal Modules**:
    * `parser.skw_parser.SKWParser`.
    * `scripter.skw_scripter.SKWScripter`.
    * `executer.skw_executer.SKWExecuter` (Note: The import is commented out as `todo: implement` in the provided source, but the class is used).

---

## 3. Class `Builder`

### Class Overview

This is the sole class in the module. An instance of `Builder` represents the master controller for all build-related activities.

### Attributes

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `build_dir` | `str` | The absolute path to the main build directory, read from `builder.toml`. |
| `package_dir` | `str` | The absolute path for storing final packages, read from `builder.toml`. |
| `profiles_dir` | `str` | The absolute path to the directory containing all book and profile configurations, read from `builder.toml`. |
| `skel_dir` | `str` | The absolute path to the directory containing skeleton configuration files (`*.skel`). |

### Methods

#### `__init__(self, config_path="builder.toml", skel_dir="src/config/skel")`

* **Purpose**: Initializes the `Builder` object.
* **Logic**:
    1.  Checks for the existence of `builder.toml`; if not found, exits with an error.
    2.  Parses `builder.toml` using `tomllib` to load path configurations.
    3.  Constructs and stores absolute paths for `build_dir`, `package_dir`, `profiles_dir`, and `skel_dir`.
    4.  Ensures that the `build_dir` and `package_dir` exist, creating them if necessary.

#### Project Scaffolding Methods

* **`add_book(self, name)`**:
    * **Purpose**: Creates the directory structure and initial configuration for a new book.
    * **Logic**: Creates a directory for the new book under `self.profiles_dir` and copies `book.toml.skel` into it as `book.toml`.
* **`add_profile(self, book, profile)`**:
    * **Purpose**: Creates a new build profile within an existing book.
    * **Logic**: Creates a subdirectory for the profile and populates it by copying all skeleton files (`parser.toml`, `scripter.toml`, `executer.toml`, and `*.script` templates) from `self.skel_dir`.

#### Book Management Methods

* **`install_book(self, book)`**:
    * **Purpose**: Clones or updates the source material for a book and generates the required XML file.
    * **Logic**:
        1.  Loads the book's configuration from its `book.toml` file.
        2.  Uses `subprocess` to run `git clone` or `git pull` to fetch the source repository.
        3.  Runs `git checkout` to switch to the configured version.
        4.  Executes the configured `make_command` using `subprocess` to generate the final XML file.

#### Pipeline Execution Methods

* **`parse_book(self, book, profile)`**:
    * **Purpose**: Invokes the parsing stage of the pipeline.
    * **Logic**: Instantiates `SKWParser` with the current context and calls its `run()` method.
* **`script_book(self, book, profile)`**:
    * **Purpose**: Invokes the scripting stage.
    * **Logic**: Instantiates `SKWScripter` and calls its `run()` method.
* **`execute_book(self, book, profile, auto_confirm=False)`**:
    * **Purpose**: Invokes the execution stage.
    * **Logic**: Instantiates `SKWExecuter` with the current context and the `auto_confirm` flag, then calls its `run_all()` method.

---

## 4. Command-Line Interface (CLI)

The script uses the `argparse` library to define a set of subcommands that map directly to the methods of the `Builder` class.

| Command | Arguments | Description |
| :--- | :--- | :--- |
| `list-books` | (none) | Lists all available books. |
| `list-profiles` | `--book` | Lists all profiles for a given book. |
| `add-book` | `--name` | Creates a new book structure. |
| `add-profile` | `--book`, `--name` | Creates a new profile within a book. |
| `install-book` | `--book` | Downloads/updates the source material for a book. |
| `parse` | `--book`, `--profile` | Runs the parser stage. |
| `script` | `--book`, `--profile` | Runs the scripter stage. |
| `execute` | `--book`, `--profile`, `[--yes]` | Runs the execution stage. The `--yes` flag enables auto-confirmation for dangerous actions. |
