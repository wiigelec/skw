Git Source Builder Module Specification

1. Goal

The primary goal of this module is to provide a reliable, automated, and configurable method for:

Reading build parameters from a TOML configuration file.

Cloning a specified Git repository.

Checking out a specific version (tag, branch, or commit hash).

Executing a defined build command within the resulting source directory.

2. Dependencies

Dependency

Type

Notes

python

3.11+ (recommended)

Utilizes tomllib (or toml for older versions).

tomllib

Python Standard Library

Used for parsing the TOML configuration.

subprocess

Python Standard Library

Used for executing git and the build command.

git

External Executable

Must be available in the system's PATH.

os, shutil

Python Standard Library

Used for directory creation/cleanup.

3. Configuration File Format (TOML)

The module must accept a single TOML file path. The TOML file must contain two mandatory top-level tables: [git] and [build].

A. [git] Table (Source Control)

Key

Type

Description

repo_url

String

The full URL of the Git repository to clone (e.g., https://github.com/user/project.git).

version

String

The specific Git reference to check out (e.g., main, v1.2.0, or a full commit hash).

target_dir

String

The local path where the repository will be cloned. Must be created if it does not exist.

B. [build] Table (Execution)

Key

Type

Description

command

String

The shell command to execute (e.g., "npm install && npm run build" or "make all").

output_dir

String

The destination path for final build artifacts. This path must be created by the module before running the build command.

cwd

String (Optional)

The working directory for the command. If omitted, defaults to the target_dir specified in [git].

shell

Boolean

If true, the command is executed through the shell (e.g., /bin/bash). Recommended for complex commands involving piping or chained operations (&&). Default is true.

4. Module API (GitBuilder Class)

The module will expose a single class, GitBuilder, and a main execution method.

Class: GitBuilder(config_path)

Method

Description

__init__(self, config_path)

Initializes the builder and immediately loads and validates the configuration from the given path.

_load_config(self)

Internal method to read the TOML file and store the configuration in instance attributes. Must raise a relevant exception if the file is missing or invalid.

_execute_command(self, cmd_list, work_dir, use_shell)

Internal helper for robustly executing shell commands using subprocess.run and logging command output.

_clone_repo(self)

Clones the repo_url into the target_dir. If the directory exists and is not empty, it should be cleaned up or prompt the user (for simplicity, we will overwrite/clean up).

_checkout_version(self)

Executes git checkout [version].

_run_build(self)

Executes the command defined in the [build] table.

build(self)

The main public method that orchestrates the entire process: Load -> Clone -> Checkout -> Build. Returns True on success, False on failure.

cleanup(self)

Optional public method to remove the target_dir after the build is complete.

5. Implementation Requirements

Error Handling: All subprocess calls must check return codes. Any non-zero exit code (for git or the build command) must halt the process and raise a descriptive error (e.g., BuildError, GitError).

Idempotency (Optional but Recommended): The _clone_repo method should handle both an empty and an existing non-Git target directory gracefully (e.g., by ensuring it's empty before cloning).

Logging: Key steps (Config loaded, Cloning started, Checkout successful, Build running, Build finished) should be logged to standard output.
