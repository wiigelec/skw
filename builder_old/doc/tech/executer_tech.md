# Technical Specification: skw_executer.py

> This document provides a detailed technical specification for the `SKWExecuter` module. It is intended for developers who need to understand the internal workings, data structures, and algorithms of the script. This version reflects a mature implementation with support for tiered remote repositories, package integrity verification, and rich metadata generation.

---

## 1. Overview 📜

The `SKWExecuter` class is a sophisticated execution engine designed to run the final stage of the ScratchKit build pipeline. It systematically executes shell scripts, manages build environments (host vs. chroot), and handles a complete package lifecycle. This lifecycle includes checking multiple remote repositories for cached artifacts, downloading them, creating new packages, generating rich build metadata, and uploading both the package and its metadata. The entire process is driven by a profile-specific `executer.toml` file and leverages a context-aware package naming scheme to prevent build conflicts.

---

## 2. Dependencies 📦

* **`tomllib`**: For parsing `.toml` configuration files.
* **`requests`**: For interacting with HTTP-based remote package repositories.
* **Standard Libraries**: `os`, `sys`, `json`, `tarfile`, `shutil`, `subprocess`, `pathlib`, `datetime`, `socket`, `platform`, `hashlib`.

---

## 3. Class `SKWExecuter`

### Class Overview

This is the sole class in the module. An instance of `SKWExecuter` represents a single, complete build execution job for a specific Book and Profile. It is designed for robustness and efficiency, capable of recovering from failed builds by using a local or remote cache and ensuring that each build step is idempotent through package integrity checks.

### Attributes

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `build_dir` | `Path` | The path to the main build directory. |
| `profiles_dir` | `Path` | The path to the directory containing all book/profile configs. |
| `book` | `str` | The name of the book being processed. |
| `profile` | `str` | The name of the profile being used. |
| `exec_dir` | `Path` | The root directory for all executer-related activities. |
| `logs_dir` | `Path` | The directory where execution logs for each script are stored. |
| `downloads_dir`| `Path` | A temporary directory for downloading packages from remote repositories. |
| `auto_confirm` | `bool` | A flag to auto-confirm prompts, like installing to the root directory. |
| `cfg` | `dict` | A dictionary containing the entire parsed `executer.toml` configuration. |
| `entries` | `list`| A list of dictionaries loaded from `parser_output.json`. |
| `scripts_dir` | `Path` | The path to the directory containing the scripts to be executed. |
| `upload_repo`| `str` | The target for publishing new packages (local path or `scp` target). |
| `download_repos`| `list` | An ordered list of source repositories for fetching cached packages. |
| `chroot_dir` | `Path` | The path to the chroot environment. |
| `default_extract_dir` | `str` | The default installation directory for host-mode packages. |
| `require_confirm_root`| `bool`| If `True`, prompts the user before installing a package to `/`. |

### Methods

#### `run_all(self)`

* **Purpose**: The main execution method that drives the entire build pipeline.
* **Algorithm**:
    1.  Gets a sorted list of all `.sh` files from `self.scripts_dir`.
    2.  Iterates through each `script`.
    3.  **For each script, it performs the following steps**:
        a.  Finds the script's metadata and determines its unique, context-aware package filename via `_pkg_filename()`.
        b.  **Cache Check**: Calls `_package_exists()` to check if the package's metadata exists in the `download_repos`. If it does, it calls `_install_package()` (which includes a checksum verification), logs the skip, and `continue`s to the next script.
        c.  **Build**: If the package is not found, it runs the script via `_run_script()`.
        d.  **Package & Deploy**: If the script was successful and marked for packaging, it calls `_create_archive()` to create the package and metadata, `_install_package()` to install from the new archive, and `_upload_package()` to publish both.

#### `_pkg_filename(self, entry)`

* **Purpose**: Generates a unique, context-aware package filename.
* **Logic**: Uses the `package_name_template` from the configuration and Python's string `format()` method, substituting placeholders like `{book}`, `{profile}`, and `{chapter_id}`. This is the core of the context-aware caching system.

#### `_create_archive(self, destdir, pkg_file, entry, exec_mode)`

* **Purpose**: Creates a compressed tarball from a `destdir` and generates a companion metadata file.
* **Logic**:
    1.  **Archive Creation**: Creates the tarball using the `tarfile` library.
    2.  **Checksum**: Calculates the SHA256 checksum of the newly created archive by calling `_sha256_file()`.
    3.  **Metadata Collection**: Gathers a comprehensive dictionary of build metadata, including the package checksum, timestamps, host information, and a file manifest generated by `_list_files()`.
    4.  **Metadata Serialization**: Writes the metadata dictionary to a `.meta.json` file.

#### `_package_exists(self, pkg_file)`

* **Purpose**: Checks for the existence of a package's **metadata file** across the tiered `download_repos`.
* **Logic**:
    * Iterates through the `download_repos` list in order.
    * For each repo, it checks for the `.meta.json` file.
        * If the repo is an HTTP URL, it sends an HTTP `HEAD` request.
        * If the repo is a local path, it performs a `Path.exists()` check.
    * The first repo where the metadata is found is stored in an instance variable (`_found_repo`), and the method returns `True`. If the loop completes without a find, it returns `False`.

#### `_install_package(self, pkg_file, entry)`

* **Purpose**: Downloads (if necessary), verifies, and extracts a package to the correct target directory.
* **Logic**:
    1.  **Get Artifacts**: Determines if the repo is remote (HTTP) or local. If remote, it downloads both the package tarball and its `.meta.json` file.
    2.  **Verify Integrity**: Loads the metadata from the JSON file and retrieves the `sha256` checksum. It then calculates the checksum of the downloaded tarball using `_sha256_file()` and compares the two. The script exits with an error if they do not match.
    3.  **Determine Target Directory**: Calculates the installation path based on execution mode (`chroot` or `host`) and configuration overrides.
    4.  **Extract**: Uses the `tarfile` library to extract the verified archive.

#### `_upload_package(self, archive)`

* **Purpose**: Publishes a newly created package and its metadata file to the configured `upload_repo`.
* **Logic**:
    * It prohibits HTTP uploads.
    * If the repo path contains a `:`, it assumes an `scp` target and uses `subprocess.check_call` to upload both the archive and its `.meta.json` file.
    * Otherwise, it assumes a local path and uses `shutil.copy2` for both files.
