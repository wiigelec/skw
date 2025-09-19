# Configuration Reference: executer.toml

> The **`executer.toml`** file is the configuration hub for the `SKWExecuter` module, the final and most critical stage of the ScratchKit build pipeline. It governs the entire execution lifecycle, including environment management (host vs. chroot), remote and local caching, package creation, and deployment.

---

## `[main]` section

This section contains the primary configuration for the execution engine.

### **`chroot_dir`**

* **Type**: `String`
* **Description**: The file system path where the chroot environment will be created and managed. The executer script uses this path as the root for all `chroot` commands.
* **Example**: `chroot_dir = "${build_dir}/chroot"`

### **`upload_repo`**

* **Type**: `String`
* **Description**: A single destination for publishing newly created packages and their metadata. It supports local filesystem paths or remote servers via SCP (e.g., `user@host:/path/`). HTTP is not a supported upload target.
* **Example**: `upload_repo = "/var/lib/skw/packages"`

### **`download_repos`**

* **Type**: `Array of Strings`
* **Description**: An ordered list of repositories to check for pre-built packages, enabling tiered caching. The executer checks each repository in sequence and uses the first one where a package's metadata is found. It supports local paths and HTTP(S) URLs.
* **Example**: `download_repos = [ "/var/lib/skw/packages", "http://mirror1.example.com/packages" ]`

### **`package_format`**

* **Type**: `String`
* **Description**: The compression format for created packages. Supported values are `tar`, `tar.gz`, and `tar.xz`.
* **Example**: `package_format = "tar.xz"`

### **`package_name_template`**

* **Type**: `String`
* **Description**: A template string that defines the unique, context-aware filename for each package. This is critical for preventing naming collisions between different build stages (e.g., cross-tools vs. final system). It supports placeholders like `{book}`, `{profile}`, `{chapter_id}`, `{section_id}`, `{package_name}`, and `{package_version}`.
* **Example**: `package_name_template = "${book}-${profile}-${chapter_id}-${package_name}-${package_version}"`

### **`default_extract_dir`**

* **Type**: `String`
* **Description**: The default directory where packages will be installed when running in "host" mode (i.e., not in chroot). This can be overridden for specific packages, sections, or chapters in the `[extract.targets]` table.
* **Example**: `default_extract_dir = "/"`

### **`require_confirm_root`**

* **Type**: `Boolean`
* **Description**: A safety feature. If `true`, the executer will prompt the user for confirmation before installing a package to the root directory (`/`) of the host system. This can be bypassed with the `--yes` flag on the command line.
* **Example**: `require_confirm_root = true`

---

## Execution and Packaging Rules

These sections define which scripts run in which environment and which ones should produce a distributable package.

### **`[chroot]`** and **`[host]`**

* **Description**: These tables contain lists of packages, sections, or chapters that should be forced to run in a specific execution mode (`chroot` or `host`).
* **Keys**: `packages`, `sections`, `chapters` (each is an array of strings).
* **Example**: `[chroot] \n packages = ["glibc", "gcc"]`

### **`[package]`** and **`[packages.exclude]`**

* **Description**: These tables control which build steps will result in the creation of a package archive. The `[package]` table defines what to *include*, while `[packages.exclude]` defines explicit exceptions that take precedence.
* **Keys**: `packages`, `sections`, `chapters`.
* **Example**: `[package] \n chapters = ["05"]` would package everything in chapter 5. `[packages.exclude] \n sections = ["ch-tools-changingowner"]` would then exclude that specific section from being packaged.

---

## `[extract.targets]` section

This section allows you to override the `default_extract_dir` for specific host-mode installations. This is particularly useful for multi-stage builds where initial tools need to be installed into a temporary location (e.g., `/tools`) instead of the final root filesystem.

* **Description**: Defines target extraction directories for packages, sections, or chapters.
* **Keys**: `packages`, `sections`, `chapters` (each is a table mapping an ID to a path).
* **Example**: `[extract.targets] \n packages = { gcc = "/tools", glibc = "/tools" }` ensures that the `gcc` and `glibc` packages are installed into `/tools` instead of `/`.
