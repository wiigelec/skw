# Functional Specification: builder.py

> The **`builder.py`** script is the master controller and command-line interface (CLI) for the ScratchKit (SKW) build system. It orchestrates the entire build pipeline by initializing the main `Builder` class and delegating tasks to the specialized `SKWParser`, `SKWScripter`, and `SKWExecuter` modules.

---

## Core Responsibilities 🎯

* **Configuration Loading**: Reads and interprets the main `builder.toml` file to get the necessary paths for the build, package, and profiles directories.
* **Command-Line Interface**: Provides a user-friendly CLI for managing the entire lifecycle of a build, including project setup, execution, and inspection.
* **Workflow Orchestration**: Manages the sequential execution of the three main build stages: Parsing, Scripting, and Execution.
* **Project Scaffolding**: Automates the creation of new "Books" and "Profiles," setting up the necessary directory structure and copying skeleton configuration files to guide the user.
* **Book Source Management**: Handles the cloning and updating of the source XML "Book" repositories (e.g., from a Git repository) and runs the necessary commands to generate the final XML file used by the parser.

---

## Functional Requirements ✅

### Initialization

* The system must be initialized by creating an instance of the `Builder` class.
* Upon initialization, the `Builder` must locate and load `builder.toml`. The system must exit with an error if this file is not found.
* It must establish absolute paths for `build_dir`, `package_dir`, and `profiles_dir` based on the configuration and ensure these directories exist.

### Command-Line Interface

The system must provide the following commands, managed through `argparse`:

* **`list-books`**:
    * Lists all available books by scanning the subdirectories within the `profiles_dir`.
* **`list-profiles --book <book>`**:
    * Lists all available profiles for a specified book by scanning its subdirectories.
* **`add-book --name <name>`**:
    * Creates a new directory for the book under `profiles_dir`.
    * Copies the `book.toml.skel` skeleton file into the new book's directory.
* **`add-profile --book <book> --name <name>`**:
    * Creates a new profile directory under the specified book.
    * Copies all skeleton configuration files (`parser.toml`, `scripter.toml`, `executer.toml`) and script templates into the new profile directory.
* **`install-book --book <book>`**:
    * Reads the `book.toml` for the specified book to get the repository path, version, and build command.
    * Clones the repository into the build directory if it doesn't exist, or pulls the latest changes if it does.
    * Checks out the specified version (branch or tag).
    * Executes the configured `make_command` to generate the final XML book file.
* **`parse --book <book> --profile <profile>`**:
    * Instantiates the `SKWParser` with the correct context (build directories, book, and profile) and calls its `run()` method.
* **`script --book <book> --profile <profile>`**:
    * Instantiates the `SKWScripter` and calls its `run()` method.
* **`execute --book <book> --profile <profile> [--yes]`**:
    * Instantiates the `SKWExecuter` and calls its `run_all()` method.
    * Must pass an `auto_confirm` flag to the executer if the `--yes` argument is provided to bypass interactive prompts.
