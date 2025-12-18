import os
import sys
import toml
import yaml
import re
import shutil
from glob import glob
from pathlib import Path
from .depsolver import DependencySolver

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
        raw_script_dir = self.cfg.get("main", {}).get("script_dir", "UNDEFINED").format(book=self.book,profile=self.profile)
        if raw_script_dir == "UNDEFINED":
            sys.exit("Error: 'script_dir' is not defined in [main] section of skwscripter.toml")
        self.script_dir = Path(raw_script_dir).expanduser().resolve()
        os.makedirs(self.script_dir, exist_ok=True)
        # Delete contents
        for item in self.script_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    # -------------------
    # Main Execution
    # -------------------
    def run(self):
        parser_dir = self.parser_dir
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

        has_build_order = any((e.get("build_order") or "").strip() for e in entries)

        if has_build_order:
            self._run_linear_mode(entries)
        else:
            self._run_dependency_mode(entries)
        
        
    # -------------------
    # Linear Mode
    # -------------------
    def _run_linear_mode(self, entries):
        # Validation
        for e in entries:
            if self._should_generate_script(e) and not (e.get("build_order") or "").strip():
                sys.exit(f"Error: build_order is required in linear mode (missing for: {e.get('name')})")

        # Sort by build_order (string), then deterministic tiebreakers
        entries.sort(key=lambda e: (
            (e.get("build_order") or "").strip(),
            (e.get("chapter_id") or ""),
            (e.get("section_id") or ""),
            (e.get("name") or ""),
        ))
        print(f"[INFO] Linear mode active - {len(entries)} entries ordered by build_order.")

        self._generate_scripts(entries)


    # -------------------
    # Dependency Mode
    # -------------------
    def _run_dependency_mode(self, entries):
        print("[INFO] No build_order fields detected - switching to dependency mode.")
    
        # Get alias file path
        raw_alias_file = self.cfg.get("main", {}).get("alias_file", "aliases.toml")
        alias_file = raw_alias_file.format(
            profiles_dir=self.profiles_dir,
            book=self.book,
            profile=self.profile,
            build_dir=self.build_dir,
        )
        alias_file = Path(alias_file).expanduser().resolve()
    
        include_classes = self.cfg.get("main", {}).get("include_classes", ["required", "recommended"])
        target = self.cfg.get("main", {}).get("target")
    
        if not target:
            sys.exit("Error: [main].target must be defined in skwscripter.toml for dependency mode.")
    
        # Build dependency tree
        solver = DependencySolver(target, self.parser_dir, alias_file, include_classes)
        tree = solver.build_full_phase_tree()
        flat = solver.flatten_phases(tree)
    
        ordered_names = (
            flat["bootstrap_pass1"]
            + flat["buildtime"]
            + flat["target"]
            + flat["bootstrap_pass2"]
            + flat["runtime"]
        )
        print(f"[INFO] Dependency tree resolved - {len(ordered_names)} total packages.")
    
        # Load aliases for reverse lookup
        try:
            alias_data = toml.load(alias_file)
            aliases = alias_data.get("aliases", {})
        except Exception as e:
            sys.exit(f"[ERROR] Failed to load alias file {alias_file}: {e}")
    
        # Reverse alias: map canonical (YAML base) -> alias key
        reverse_alias = {}
        for alias_key, canonical_name in aliases.items():
            if isinstance(canonical_name, str) and canonical_name:
                reverse_alias[canonical_name.lower()] = alias_key.lower()
    
        # Build name map from YAML entries
        name_map = {e["name"].lower(): e for e in entries if e.get("name")}
    
        # Extend name map with alias entries
        for canonical, alias in reverse_alias.items():
            # Exact match
            if canonical in name_map and alias not in name_map:
                name_map[alias] = name_map[canonical]
                continue
    
            # Prefix match (e.g. canonical 'glib-2.82.5' ? YAML 'glib')
            for key in list(name_map.keys()):
                if canonical.startswith(key) and alias not in name_map:
                    name_map[alias] = name_map[key]
                    break
    
        # Match dependency order to YAML entries
        ordered_entries = []
        for pkg in ordered_names:
            pkg_lower = pkg.lower()
            if pkg_lower in name_map:
                ordered_entries.append(name_map[pkg_lower])
            else:
                print(f"[WARN] Package '{pkg}' not found among YAML entries.")
    
        print(f"[INFO] Matched {len(ordered_entries)} of {len(ordered_names)} packages to YAML entries.")
    
        # Generate scripts in dependency order
        self._generate_scripts(ordered_entries)


    # -------------------
    # Script Generation (Shared)
    # -------------------
    def _generate_scripts(self, ordered_entries):
        script_dir = self.script_dir
        for idx, entry in enumerate(ordered_entries, start=1):
            if not self._should_generate_script(entry):
                continue

            template_content = self._select_template(entry)
            script_content = self._expand_template(entry, template_content)
            script_content = self._apply_regex(entry, script_content)

            order = entry.get("build_order") or f"{idx:04d}"
            name = entry.get("name") or entry.get("chapter_id")
            ver = entry.get("version") or entry.get("section_id")
            if not name or not ver:
                sys.exit(f"Error: missing name or version for script generation: {entry}")

            script_name = f"{order}_{self._slug(name)}_{self._slug(ver)}.sh"
            script_path = os.path.join(script_dir, script_name)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)

        print(f"[INFO] Scripter complete. Scripts written to {script_dir}")
        
        
    # -------------------   
    def _slug(self, s: str) -> str:
        s = str(s).strip().lower()
        s = s.replace("/", "_").replace("\\", "_")
        s = re.sub(r"\s+", "-", s)
        s = re.sub(r"[^a-z0-9._+-]+", "-", s)
        s = re.sub(r"-{2,}", "-", s).strip("-")
        return s or "unnamed"
        

    # -------------------
    # Script filtering
    # -------------------
    def _should_generate_script(self, entry):
        """Determine if the script should be generated based on TOML filter sections."""
        filters = {
            "chapter_id": self.cfg.get("chapter_filters", {}),
            "section_id": self.cfg.get("section_filters", {}),
            "name": self.cfg.get("package_filters", {}),
        }

        for key, section in filters.items():
            ident = entry.get(key)
            if not ident:
                continue

            include = section.get("include", [])
            exclude = section.get("exclude", [])

            # Inclusion filter
            if include and ident not in include:
                return False
            # Exclusion filter
            if exclude and ident in exclude:
                return False

        return True

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
            "name": raw.get("name", ""),
            "version": raw.get("version", ""),
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
        pkg_key = entry.get("name")

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

        for key in [entry.get("chapter_id"), entry.get("section_id"), entry.get("name")]:
            if key and key in self.cfg and "template" in self.cfg[key]:
                template_file = self.cfg[key]["template"]

        path = os.path.join(self.profiles_dir, self.book, self.profile, template_file)
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
        else:
            print(f"Warning: template {path} not found, falling back to default.")
            return self.default_template
