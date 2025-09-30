# Configuring the Parser to Create Custom Scripts

The **ScratchKit parser** is designed not only to process the main XML *Book* but also to inject custom build steps that are not defined in the source XML. This feature allows you to add your own packages, run arbitrary commands, or create specialized setup scripts without modifying the original Book.

This is accomplished by defining custom package configurations in one or more separate **TOML files** and then referencing them from your main `parser.toml`.

---

## How It Works

The process involves two main steps:

1. **Enabling Custom Code in `parser.toml`**  
   Add a `[custom_code]` section to your profile's `parser.toml` file. This section contains a single key, `configs`, which is a list of filenames for your custom package definitions.

2. **Creating a Custom Package File**  
   Create a new `.toml` file (e.g., `custom-packages.toml`) in your profile directory. This file contains the definitions for your custom build steps.

The parser first processes the main XML book as usual. Afterward, it reads the files listed in the `configs` array and injects the build steps defined within them into the final `parser_output.json`.

---

## Step 1: Update `parser.toml`

To enable custom scripts, add the following section:

```toml
# ================================================================
# Custom Code Injection
# ================================================================

[custom_code]
# A list of TOML files in the profile directory that define custom packages.
configs = ["custom-packages.toml"]
```

You can list multiple files if you wish to organize your custom scripts into different categories.

---

## Step 2: Create the Custom Package File

Next, create the file `custom-packages.toml` (or whatever name you specified in the `configs` list) within the same profile directory. This file will contain an array of tables, where each table defines a single custom script.

Each custom package can have the following keys:

- `name`: The name of your custom package or script.  
- `version`: An optional version number.  
- `section_id`: A unique ID for the script, which will be used in the generated script's filename (e.g., `custom-setup-firewall`).  
- `chapter_id`: The chapter this script belongs to (a good practice is to use `"custom"` for all custom scripts).  
- `commands`: A list of inline shell commands to be executed.  
- `xpath_commands`: A list of XPath expressions that extract commands from the main XML Book. Useful for reusing commands from the book in a different context.  

---

## Example: `custom-packages.toml`

Here is an example file that defines two custom scripts:

```toml
# ================================================================
# Custom Package Definitions
# ================================================================

# Script 1: Creates a custom directory and welcome message.
# This uses inline commands.
[[custom_packages]]
name = "welcome-message"
version = "1.0"
section_id = "custom-welcome"
chapter_id = "custom"
commands = [
  "mkdir -pv /etc/skw",
  "echo 'Welcome to your custom-built SKW system!' > /etc/skw/welcome.txt"
]

# Script 2: A custom firewall setup script.
# This script reuses an existing command from the LFS book via XPath.
[[custom_packages]]
name = "firewall-setup"
version = "1.0"
section_id = "custom-firewall"
chapter_id = "custom"
xpath_commands = [
  "//sect1[@id='ch-config-firewall']//screen/userinput"
]
```

---

## Final Notes

Once these files are in place, running the parse command for this profile will include these two new scripts in the `parser_output.json`, ready for the scripter and executer stages.
