# Git Source Builder Module Specification

## 1. Goal

The primary goal of this module is to provide a reliable, automated, and configurable method for:

1. Reading build parameters from a single TOML configuration table.
2. Cloning or updating a specified Git repository.
3. Checking out a specific version (tag, branch, or commit hash).
4. Executing a defined build command within the resulting source directory, with the expected output file noted for informational purposes.

## 2. Dependencies

| Dependency | Type | Notes | 
|---|---|---|
| `python` | 3.11+ (recommended) | Utilizes `tomllib` (or `toml` for older versions). | 
| `tomllib` | Python Standard Library | Used for parsing the TOML configuration. | 
| `subprocess` | Python Standard Library | Used for executing `git` and the build command. | 
| `git` | External Executable | Must be available in the system's PATH. | 
| `os`, `shutil` | Python Standard Library | Used for directory creation/cleanup. | 

## 3. Configuration File Format (TOML)

The module **must** accept a single TOML file path. The TOML file must contain a single mandatory top-level table: `[config]`, which holds all necessary Git and build parameters.

### A. `[config]` Table (All Parameters)

| Key | Type | Description | 
|---|---|---|
| `repo_url` | String | The full URL of the Git repository to clone (e.g., `https://git.linuxfromscratch.org/lfs.git`). | 
| `version` | String | The specific Git reference to check out (e.g., `12.4`, `main`, or a full commit hash). | 
| `target_dir` | String | The local path where the repository will be cloned (e.g., `./book-git`). **Must be created if it does not exist.** | 
| `build_command` | String | The shell command to execute after checkout (e.g., `"make RENDERTMP=./output/dir REV=systemd validate"`). | 
| `output_file` | String | **The expected path and filename of the final build artifact.** This key is **for informational/reporting purposes only**; the module will not perform any filesystem actions based on this path. | 

## 4. Module API (`GitBuilder` Class)

The module will expose a single class, `GitBuilder`, and a main execution method.

| Method | Description | 
|---|---|
| `__init__(self, config_path)` | Initializes the builder and immediately loads and validates the configuration from the given path. | 
| `_load_config(self)` | Internal method to read the TOML file and store the configuration in instance attributes. **Must raise a relevant exception** if the file is missing or invalid. | 
| `_execute_command(self, command, work_dir, use_shell)` | Internal helper for robustly executing shell commands using `subprocess.run` and logging command output. | 
| `_clone_repo(self)` | Clones the `repo_url` into the `target_dir`. If the directory exists and is not empty update the repo using `git pull`. | 
| `_checkout_version(self)` | Executes `git checkout [version]`. | 
| `_run_build(self)` | Executes the command defined by `build_command`. Logs the expected `output_file` as part of the build summary. | 
| `build(self)` | The main public method that orchestrates the entire process: Load -> Clone -> Checkout -> Build. **Returns `True` on success, `False` on failure.** |

## 5. Implementation Requirements

1. **Error Handling:** All `subprocess` calls must check return codes. Any non-zero exit code (for `git` or the build command) must halt the process and raise a descriptive error (e.g., `BuildError`, `GitError`).

2. **Directory Creation:** The module must ensure the `target_dir` exists and is prepared for cloning.

3. **Logging:** Key steps (Config loaded, Cloning started, Checkout successful, Build running, Build finished) should be logged to standard output.
