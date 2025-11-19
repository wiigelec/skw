import os
import sys
import toml
import yaml
import re
from glob import glob
from pathlib import Path

class SKWScripter:
    def __init__(self, build_dir, profiles_dir, book, profile):
        self.build_dir = build_dir
        self.profiles_dir = profiles_dir
        self.book = book
        self.profile = profile

        # Load scripter.toml
        self.config_path = os.path.join(profiles_dir, book, profile, "skwscripter.toml")
        if not os.path.exists(self.config_path):
            sys.exit(f"skwscripter.toml not found for {self.config_path}. Did you copy an example config?")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg = toml.load(f)

        # Load default template
        default_template = self.cfg.get("main", {}).get("default_template", "template.script")
        self.template_path = os.path.join(profiles_dir, book, profile, default_template)
        if not os.path.exists(self.template_path):
            sys.exit(f"Default template not found: {self.template_path}. Did you copy/create script templates?")

        with open(self.template_path, "r") as f:
            self.default_template = f.read()

        # Get parser output dir
        raw_parser_dir = self.cfg.get("main", {}).get("parser_output", "UNDEFINED").format(book=self.book)
        self.parser_dir = Path(raw_parser_dir).expanduser().resolve()
        if not os.path.exists(self.parser_dir):
            sys.exit(f"Parser output dir not found: {self.parser_dir}. Did you run the parser?")

        # Get scripts dir
        raw_script_dir = self.cfg.get("main", {}).get("script_dir", "UNDEFINED").format(book=self.book)
        if raw_script_dir == "UNDEFINED":
            sys.exit("Error: 'script_dir' is not defined in [main] section of skwscripter.toml")
        self.script_dir = Path(raw_script_dir).expanduser().resolve()
        os.makedirs(self.script_dir, exist_ok=True)

    # -------------------
    # Main Execution
    # -------------------
    def run(self):

        # Get config paths
        parser_dir = self.parser_dir
        script_dir = self.script_dir

        yaml_files = sorted(glob(os.path.join(parser_dir, "*.yaml")) + glob(os.path.join(parser_dir, "*.yml")))
        if not yaml_files:
            sys.exit(f"No YAML files found in {parser_dir}")

        entries = []
        for path in yaml_files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                normalized = self._normalize_entry(raw)
                entries.append(normalized)
            except Exception as e:
                print(f"Error reading {path}: {e}")

        for idx, entry in enumerate(entries, start=1):
            if not self._should_generate_script(entry):
                continue
                
            template_content = self._select_template(entry)
            script_content = self._expand_template(entry, template_content)
            script_content = self._apply_regex(entry, script_content)

            order = entry.get("build_order") or f"{idx:04d}"
            chapter_id = entry.get("chapter_id", "chapter-unknown")
            section_id = entry.get("section_id", "section-unknown")

            script_name = f"{order}_{chapter_id}_{section_id}.sh"
            script_path = os.path.join(script_dir, script_name)

            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)

        print(f"Scripter complete. Scripts written to {script_dir}")

    # -------------------
    # Script filtering
    # -------------------
    def _should_generate_script(self, entry):
        """Only generate scripts for chapters explicitly listed in the TOML config."""
        chapter_id = entry.get("chapter_id", "")
        if not chapter_id:
            return False

        # Chapters defined in TOML (excluding main/global)
        configured_chapters = [
            k for k in self.cfg.keys()
            if k not in ("main", "global")
        ]

        return chapter_id in configured_chapters

    # -------------------
    # Normalization
    # -------------------
    def _normalize_entry(self, raw):
        def normalize_source_block(block):
            """Ensures source-like dicts become list[dict(url, checksum)]"""
            if not block:
                return []
            urls = block.get("url", [])
            sums = block.get("checksum", [])
            if isinstance(urls, str):
                urls = [urls]
            if isinstance(sums, str):
                sums = [sums]
            while len(sums) < len(urls):
                sums.append("")
            return [{"url": u, "checksum": c} for u, c in zip(urls, sums)]

        def normalize_dependencies(deps):
            base = {"required": [], "recommended": [], "optional": [], "runtime": []}
            if not deps:
                return base
            for k in base.keys():
                val = deps.get(k, [])
                if isinstance(val, str):
                    val = [v.strip() for v in val.split(",") if v.strip()]
                base[k] = val
            return base

        def ensure_list(val):
            if val is None:
                return []
            if isinstance(val, list):
                return val
            return [val]

        return {
            "package_name": raw.get("name", ""),
            "package_version": raw.get("version", ""),
            "book_title": (
                " ".join(raw["book_title"]) if isinstance(raw.get("book_title"), list)
                else raw.get("book_title", "")
            ),
            "book_ver": raw.get("book_ver", ""),
            "book_rev": raw.get("book_rev", ""),
            "chapter_id": raw.get("chapter_id", ""),
            "section_id": raw.get("section_id", ""),
            "build_order": raw.get("build_order", ""),
            "source": normalize_source_block(raw.get("source")),
            "patches": normalize_source_block(raw.get("patches")),
            "additional_downloads": normalize_source_block(raw.get("additional_downloads")),
            "dependencies": normalize_dependencies(raw.get("dependencies")),
            "build_instructions": ensure_list(raw.get("build_instructions")),
        }

    # -------------------
    # Template Expansion
    # -------------------
    def _expand_template(self, entry, template_content):
        content = template_content

        def replace_placeholder(match):
            key = match.group(1)
            parts = key.split(".")
            val = entry
            for p in parts:
                if isinstance(val, dict) and p in val:
                    val = val[p]
                elif isinstance(val, list):
                    try:
                        val = val[int(p)]
                    except (ValueError, IndexError):
                        return ""
                else:
                    return ""
            if isinstance(val, list):
                if key == "build_instructions":
                    return "\n".join(val)
                return " ".join(str(v) for v in val)
            return str(val) if val is not None else ""

        return re.sub(r"{{([^}]+)}}", replace_placeholder, content)

    # -------------------
    # Regex Transforms
    # -------------------
    def _apply_regex(self, entry, content):
        transforms = []
        transforms += self.cfg.get("global", {}).get("regex", [])

        chap_key = entry.get("chapter_id")
        sec_key = entry.get("section_id")
        pkg_key = entry.get("package_name")

        if chap_key and chap_key in self.cfg:
            transforms += self.cfg[chap_key].get("regex", [])
        if sec_key and sec_key in self.cfg:
            transforms += self.cfg[sec_key].get("regex", [])
        if pkg_key and pkg_key in self.cfg:
            transforms += self.cfg[pkg_key].get("regex", [])

        for pattern in transforms:
            if isinstance(pattern, str):
                pattern = [pattern]
            for p in pattern:
                try:
                    if len(p) > 2 and (p.startswith("s") or p.startswith("r")):
                        mode = p[0]
                        delim = p[1]
                        parts = p.split(delim)
                        if parts and parts[-1] == "":
                            parts = parts[:-1]
                        if len(parts) >= 3:
                            old, new = parts[1], parts[2]
                            if mode == "s":
                                content = re.sub(re.escape(old), new, content)
                            elif mode == "r":
                                content = re.sub(old, new, content)
                except Exception as e:
                    print(f"Regex error on {p}: {e}")
        return content

    # -------------------
    # Template Selection
    # -------------------
    def _select_template(self, entry):
        template_file = self.cfg.get("main", {}).get("default_template", "template.script")

        for key in [entry.get("chapter_id"), entry.get("section_id"), entry.get("package_name")]:
            if key and key in self.cfg and "template" in self.cfg[key]:
                template_file = self.cfg[key]["template"]

        path = os.path.join(self.profiles_dir, self.book, self.profile, template_file)
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
        else:
            print(f"Warning: template {path} not found, falling back to default.")
            return self.default_template
