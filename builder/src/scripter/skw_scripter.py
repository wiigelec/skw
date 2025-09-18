import os
import sys
import json
import tomllib
import re


class SKWScripter:
    def __init__(self, build_dir, profiles_dir, book, profile):
        self.build_dir = build_dir
        self.profiles_dir = profiles_dir
        self.book = book
        self.profile = profile

        # Load scripter.toml
        self.config_path = os.path.join(profiles_dir, book, profile, "scripter.toml")
        if not os.path.exists(self.config_path):
            sys.exit(f"scripter.toml not found for {book}/{profile}")

        with open(self.config_path, "rb") as f:
            self.cfg = tomllib.load(f)

        # Load default template
        default_template = self.cfg.get("main", {}).get("default_template", "template.script")
        self.template_path = os.path.join(profiles_dir, book, profile, default_template)
        if not os.path.exists(self.template_path):
            sys.exit(f"Default template not found: {self.template_path}")

        with open(self.template_path, "r") as f:
            self.template = f.read()

    def run(self):
        #parser_json_path = self._substitute(self.cfg["main"]["parser_json"])
        parser_json_path = f"build/parser/{self.book}/{self.profile}/parser_output.json"
        #script_dir = self._substitute(self.cfg["main"]["script_dir"])
        script_dir = f"build/scripter/{self.book}/{self.profile}/scripts"

        if not os.path.exists(parser_json_path):
            sys.exit(f"Parser output not found: {parser_json_path}")

        os.makedirs(script_dir, exist_ok=True)

        with open(parser_json_path, "r", encoding="utf-8") as f:
            entries = json.load(f)

        for idx, entry in enumerate(entries, start=1):

            # Pick template (override-aware)
            template = self._select_template(entry)
            
            # Expand template
            script_content = self._expand_template(entry)

            # Apply regex transforms
            script_content = self._apply_regex(entry, script_content)

            # Zero-padded order
            order = f"{idx:04d}"
            section_id = entry["section_id"] or f"step{idx}"
            script_name = f"{order}_{section_id}.sh"

            script_path = os.path.join(script_dir, script_name)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)

        print(f"Scripter complete. Scripts written to {script_dir}")

    # -------------------
    # Template Expansion
    # -------------------
    def _expand_template(self, entry):
        content = self.template

        def replace_placeholder(match):
            key = match.group(1)
            parts = key.split(".")
            val = entry
            for p in parts:
                if isinstance(val, dict) and p in val:
                    val = val[p]
                else:
                    return ""  # missing key

            # Flatten lists
            if isinstance(val, list):
                if key == "build_instructions":
                    return "\n".join(val)
                else:
                    return " ".join(val)
            return str(val) if val is not None else ""

        return re.sub(r"{{([^}]+)}}", replace_placeholder, content)

    # -------------------
    # Regex Transforms
    # -------------------
    def _apply_regex(self, entry, content):
        transforms = []
        transforms += self.cfg.get("global", {}).get("regex", [])
        transforms += self.cfg.get(entry["chapter_id"], {}).get("regex", [])
        transforms += self.cfg.get(entry["section_id"], {}).get("regex", [])
        if entry["package_name"]:
            transforms += self.cfg.get(entry["package_name"], {}).get("regex", [])

        for pattern in transforms:
            if isinstance(pattern, str):
                pattern = [pattern]
            for p in pattern:
                try:
                    if p.startswith("s/") or p.startswith("s@"):
                        delim = p[1]
                        _, old, new, *_ = p.split(delim)
                        content = re.sub(old, new, content)
                except Exception as e:
                    print(f"Regex error on {p}: {e}")
        return content

    # -------------------
    # Template Selection
    # -------------------
    def _select_template(self, entry):
        # Start with default
        template_file = self.cfg.get("main", {}).get("default_template", "template.script")

        # Priority: package > section > chapter
        if entry.get("package_name"):
            pkg_key = f"package.{entry['package_name']}"
            if pkg_key in self.cfg and "template" in self.cfg[pkg_key]:
                template_file = self.cfg[pkg_key]["template"]

        sec_key = f"section_id.{entry['section_id']}"
        if sec_key in self.cfg and "template" in self.cfg[sec_key]:
            template_file = self.cfg[sec_key]["template"]

        chap_key = f"chapter_id.{entry['chapter_id']}"
        if chap_key in self.cfg and "template" in self.cfg[chap_key]:
            template_file = self.cfg[chap_key]["template"]

        path = os.path.join(self.profiles_dir, self.book, self.profile, template_file)
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
        else:
            print(f"Warning: template {path} not found, falling back to default.")
            return self.default_template

    def _substitute(self, value: str) -> str:
        substitutions = {
            "${book}": self.book,
            "${profile}": self.profile,
            "${build_dir}": self.build_dir,
        }
        for key, val in substitutions.items():
            value = value.replace(key, val)
        return value

