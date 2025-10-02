import os
import json
import tomllib
from string import Template
from lxml import etree
from dataclasses import dataclass, asdict
from skw_depresolver import SKWDepResolver


class ParserConfigError(Exception):
    """Raised when parser configuration is invalid or missing."""


class ParserInputError(Exception):
    """Raised when input data (e.g., XML) is missing or invalid."""


@dataclass
class ParsedEntry:
    source_book: str
    chapter_id: str
    section_id: str
    package_name: str
    package_version: str
    sources: dict
    dependencies: dict
    build_instructions: list


class SKWParser:
    def __init__(self, build_dir, profiles_dir, book, profile):
        self.build_dir = build_dir
        self.profiles_dir = profiles_dir
        self.book = book
        self.profile = profile

        self.config_path = os.path.join(
            profiles_dir, book, profile, "parser.toml"
        )

        if not os.path.exists(self.config_path):
            raise ParserConfigError(
                f"parser.toml not found for book '{book}' profile '{profile}'."
            )

        with open(self.config_path, "rb") as f:
            self.cfg = tomllib.load(f)

    # =====================================================
    # Main workflow (Steps 1–5)
    # =====================================================
    def run(self):
        # Step 1: Parse book -> ParsedEntry dict
        parsed_entries = self._parse_book_xml()

        # Step 2: Apply filters -> root section ids
        root_section_ids = self._get_root_sections(parsed_entries)

        # Step 3: Dependency class masks (default = none)
        section_dep_classes = self._get_dependency_classes(parsed_entries)

        # Step 4: Dependency resolution
        resolver = SKWDepResolver(
            parsed_entries=parsed_entries,
            root_section_ids=root_section_ids,
            dep_classes=section_dep_classes
        )
        ordered_build_list = resolver.resolve_build_order()

        # Step 5: Output JSON
        profile_parser_dir = os.path.join(self.build_dir, "parser", self.book, self.profile)
        os.makedirs(profile_parser_dir, exist_ok=True)
        output_file = self.cfg["main"]["output_file"]
        output_path = os.path.join(profile_parser_dir, output_file)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in ordered_build_list], f, indent=2)

        print(f"Parser complete. Ordered build plan written to {output_path}")

    # =====================================================
    # Step 1: Parse XML into ParsedEntry dict
    # =====================================================
    def _parse_book_xml(self) -> dict[str, ParsedEntry]:
        xml_path = self._substitute(self.cfg["main"]["xml_path"])

        if not os.path.exists(xml_path):
            raise ParserInputError(
                f"XML book not found at {xml_path}. Did you run install-book?"
            )

        tree = etree.parse(xml_path)
        results: dict[str, ParsedEntry] = {}

        chapter_xpath = self.cfg["xpaths"]["chapter_id"]
        section_xpath = self.cfg["xpaths"]["section_id"]

        for chap in self._safe_xpath(tree, chapter_xpath):
            chap_id = chap.get("id")

            for sec in self._safe_xpath(chap, section_xpath):
                sec_id = sec.get("id")
               
                pkg_name_expr = self._get_xpath_expr(sec_id, chap_id, "package_name")
                pkg_ver_expr = self._get_xpath_expr(sec_id, chap_id, "package_version")

                pkg_name = self._xpath_scalar(sec, pkg_name_expr)
                pkg_ver = self._xpath_scalar(sec, pkg_ver_expr)

                context = {
                    "book": self.book,
                    "chapter_id": chap_id,
                    "section_id": sec_id,
                    "package_name": pkg_name or "",
                    "package_version": pkg_ver or "",
                }

                sources = {
                    "urls": [str(x) for x in self._safe_xpath(
                        sec, self._expand_xpath(
                            self._get_xpath_expr(sec_id, chap_id, "source_urls"), context
                        )
                    )],
                    "checksums": [str(x) for x in self._safe_xpath(
                        sec, self._expand_xpath(
                            self._get_xpath_expr(sec_id, chap_id, "source_checksums"), context
                        )
                    )],
                }

                deps = {
                    "required": [str(x) for x in self._safe_xpath(sec, self._get_xpath_expr(sec_id, chap_id, "dependencies_required"))],
                    "recommended": [str(x) for x in self._safe_xpath(sec, self._get_xpath_expr(sec_id, chap_id, "dependencies_recommended"))],
                    "optional": [str(x) for x in self._safe_xpath(sec, self._get_xpath_expr(sec_id, chap_id, "dependencies_optional"))],
                    "runtime": [str(x) for x in self._safe_xpath(sec, self._get_xpath_expr(sec_id, chap_id, "dependencies_runtime"))],
                }
                deps = {k: [d.lower() for d in v] for k, v in deps.items()}
                deps = self._filter_dependencies(pkg_name, deps)

                build_instructions = self._collect_instructions(
                    sec, self._get_xpath_expr(sec_id, chap_id, "build_instructions")
                )
                

                entry = ParsedEntry(
                    source_book=self.book,
                    chapter_id=chap_id,
                    section_id=sec_id,
                    package_name=pkg_name or "",
                    package_version=pkg_ver or "",
                    sources=sources,
                    dependencies=deps,
                    build_instructions=build_instructions,
                )
                results[sec_id] = entry

        # --- Custom code packages ---
        for cfg_file in self.cfg.get("custom_code", {}).get("configs", []):
            cfg_path = os.path.join(self.profiles_dir, self.book, self.profile, cfg_file)
            if not os.path.exists(cfg_path):
                raise ParserConfigError(f"Custom config not found: {cfg_path}")

            with open(cfg_path, "rb") as f:
                custom_cfg = tomllib.load(f)

            for pkg in custom_cfg.get("custom_packages", []):
                build_instructions = pkg.get("commands", [])

                for expr in pkg.get("xpath_commands", []):
                    for node in self._safe_xpath(tree, expr):
                        cmd = "".join(node.itertext()).strip()
                        if cmd:
                            build_instructions.append(cmd)

                if not self._package_allowed(pkg["name"]):
                    continue

                deps = {"required": [], "recommended": [], "optional": [], "runtime": []}
                deps = self._filter_dependencies(pkg["name"], deps)

                entry = ParsedEntry(
                    source_book=self.book,
                    chapter_id=pkg.get("chapter_id", f"custom-{pkg['name']}"),
                    section_id=pkg.get("section_id", f"custom-{pkg['name']}"),
                    package_name=pkg["name"],
                    package_version=pkg.get("version", ""),
                    sources={"urls": [], "checksums": []},
                    dependencies=deps,
                    build_instructions=build_instructions,
                )
                results[entry.section_id] = entry

        return results

    # =====================================================
    # Step 2: Filtering
    # =====================================================
    def _get_root_sections(self, parsed_entries: dict[str, ParsedEntry]) -> list[str]:
        root_ids = []

        include_sections = self.cfg.get("section_filters", {}).get("include", [])
        root_ids.extend(include_sections)

        include_pkgs = self.cfg.get("package_filters", {}).get("include", [])
        for pkg in include_pkgs:
            for sec_id, entry in parsed_entries.items():
                if entry.package_name == pkg:
                    root_ids.append(sec_id)

        include_chaps = self.cfg.get("chapter_filters", {}).get("include", [])
        for sec_id, entry in parsed_entries.items():
            if entry.chapter_id in include_chaps:
                root_ids.append(sec_id)

       # Deduplicate while preserving order
        seen = set()
        ordered_root_ids = []
        for sec_id in root_ids:
            if sec_id not in seen:
                seen.add(sec_id)
                ordered_root_ids.append(sec_id)
    
        return ordered_root_ids

    # =====================================================
    # Step 3: Dependency class masks
    # =====================================================
    def _get_dependency_classes(self, parsed_entries: dict[str, ParsedEntry]) -> dict[str, list[str]]:
        # Global dependency classes from config
        global_deps = self.cfg.get("package_filters", {}).get("deps", [])
        return {sec_id: global_deps for sec_id in parsed_entries}

    # =====================================================
    # Helpers
    # =====================================================
    def _get_xpath_expr(self, sec_id, chap_id, key):
        # Section-specific overrides
        if sec_id in self.cfg and "xpaths" in self.cfg[sec_id]:
            if key in self.cfg[sec_id]["xpaths"]:
                return self.cfg[sec_id]["xpaths"][key]
    
        # Chapter-specific overrides
        if chap_id in self.cfg and "xpaths" in self.cfg[chap_id]:
            if key in self.cfg[chap_id]["xpaths"]:
                return self.cfg[chap_id]["xpaths"][key]
    
        # Global fallback
        return self.cfg["xpaths"].get(key)
        def _expand_xpath(self, expr, context):
            if not expr:
                return None
        return Template(expr).safe_substitute(context)

    def _filter_ok(self, value, filters):
        inc = filters.get("include", [])
        exc = filters.get("exclude", [])
        if inc and value not in inc:
            return False
        if exc and value in exc:
            return False
        return True

    def _substitute(self, value: str) -> str:
        return Template(value).safe_substitute(
            book=self.book, profile=self.profile, build_dir=self.build_dir
        )

    def _collect_instructions(self, node, expr):
        instructions = []
        for n in self._safe_xpath(node, expr):
            cmd = "".join(n.itertext()).strip()
            if cmd:
                instructions.append(cmd)
        return instructions

    def _safe_xpath(self, node, expr):
        if not expr or not str(expr).strip():
            return []
        try:
            return node.xpath(expr)
        except etree.XPathEvalError as e:
            raise ParserConfigError(f"Invalid XPath expression: {expr}") from e

    def _xpath_scalar(self, node, expr):
        if not expr or not str(expr).strip():
            return None
        try:
            result = node.xpath(expr)
            if isinstance(result, list):
                if not result:
                    return None
                return str(result[0])
            return str(result)
        except etree.XPathEvalError as e:
            raise ParserConfigError(f"Invalid XPath expression: {expr}") from e

    def _package_allowed(self, pkg_name):
        pkg_filters = self.cfg.get("package_filters", {})
        includes = pkg_filters.get("include", [])
        excludes = pkg_filters.get("exclude", [])

        if pkg_name in excludes:
            return False
        if includes and pkg_name not in includes:
            return False
        return True

    def _get_package_config(self, pkg_name):
        for pkg in self.cfg.get("package", []):
            if pkg.get("name") == pkg_name:
                return pkg
        return None

    def _filter_dependencies(self, pkg_name, deps):
        pkg_filters = self.cfg.get("package_filters", {})
        allowed_deps = pkg_filters.get("deps", [])

        pkg_cfg = self._get_package_config(pkg_name)
        if pkg_cfg and "deps" in pkg_cfg:
            allowed_deps = pkg_cfg["deps"]

        if not allowed_deps:
            return deps
        return {cls: deps.get(cls, []) for cls in allowed_deps if cls in deps}
