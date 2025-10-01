import os
import json
import tomllib
from string import Template
from lxml import etree
from dataclasses import dataclass, asdict


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
    dependencies: list
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

    def run(self):
        xml_path = self._substitute(self.cfg["main"]["xml_path"])
        output_file = self.cfg["main"]["output_file"]

        if not os.path.exists(xml_path):
            raise ParserInputError(
                f"XML book not found at {xml_path}. Did you run install-book?"
            )

        tree = etree.parse(xml_path)
        results: list[ParsedEntry] = []

        # --- Normal book parsing ---
        chapter_xpath = self.cfg["xpaths"]["chapter_id"]
        section_xpath = self.cfg["xpaths"]["section_id"]

        for chap in self._safe_xpath(tree, chapter_xpath):
            chap_id = chap.get("id")
            if not self._filter_ok(chap_id, self.cfg.get("chapter_filters", {})):
                continue

            for sec in self._safe_xpath(chap, section_xpath):
                sec_id = sec.get("id")
                if not self._filter_ok(sec_id, self.cfg.get("section_filters", {})):
                    continue

                pkg_name_expr = self._get_xpath_expr(sec_id, chap_id, "package_name")
                pkg_ver_expr = self._get_xpath_expr(sec_id, chap_id, "package_version")

                pkg_name = self._xpath_or_none(sec, pkg_name_expr)
                pkg_ver = self._xpath_or_none(sec, pkg_ver_expr)

                context = {
                    "book": self.book,
                    "chapter_id": chap_id,
                    "section_id": sec_id,
                    "package_name": pkg_name or "",
                    "package_version": pkg_ver or "",
                }

                sources = {
                    "urls": self._safe_xpath(sec, self._expand_xpath(
                        self._get_xpath_expr(sec_id, chap_id, "source_urls"), context
                    )),
                    "checksums": self._safe_xpath(sec, self._expand_xpath(
                        self._get_xpath_expr(sec_id, chap_id, "source_checksums"), context
                    )),
                }

                deps = {
                    "required": self._safe_xpath(sec, self._get_xpath_expr(sec_id, chap_id, "dependencies_required")),
                    "recommended": self._safe_xpath(sec, self._get_xpath_expr(sec_id, chap_id, "dependencies_recommended")),
                    "optional": self._safe_xpath(sec, self._get_xpath_expr(sec_id, chap_id, "dependencies_optional")),
                    "runtime": self._safe_xpath(sec, self._get_xpath_expr(sec_id, chap_id, "dependencies_runtime")),
                }

                build_instructions = self._collect_instructions(
                    sec, self._get_xpath_expr(sec_id, chap_id, "build_instructions")
                )

                results.append(
                    ParsedEntry(
                        source_book=self.book,
                        chapter_id=chap_id,
                        section_id=sec_id,
                        package_name=pkg_name or "",
                        package_version=pkg_ver or "",
                        sources=sources,
                        dependencies=deps,
                        build_instructions=build_instructions,
                    )
                )

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

                results.append(
                    ParsedEntry(
                        source_book=self.book,
                        chapter_id=pkg.get("chapter_id", f"custom-{pkg['name']}"),
                        section_id=pkg.get("section_id", f"custom-{pkg['name']}"),
                        package_name=pkg["name"],
                        package_version=pkg.get("version", ""),
                        sources={"urls": [], "checksums": []},
                        dependencies={"required": [], "recommended": [], "optional": [], "runtime": []},
                        build_instructions=build_instructions,
                    )
                )

        # --- Write output ---
        profile_parser_dir = os.path.join(self.build_dir, "parser", self.book, self.profile)
        os.makedirs(profile_parser_dir, exist_ok=True)
        output_path = os.path.join(profile_parser_dir, output_file)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in results], f, indent=2)

        print(f"Parser complete. Output written to {output_path}")

    # --- Helpers ---
    def _get_xpath_expr(self, sec_id, chap_id, key):
        if sec_id in self.cfg and "xpaths" in self.cfg[sec_id]:
            return self.cfg[sec_id]["xpaths"].get(key)
        if chap_id in self.cfg and "xpaths" in self.cfg[chap_id]:
            return self.cfg[chap_id]["xpaths"].get(key)
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

    def _xpath_or_none(self, node, expr):
        results = self._safe_xpath(node, expr)
        if not results:
            return None
        return str(results[0])

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
        """Run xpath safely: skip if None/empty, raise ParserConfigError if invalid."""
        if not expr or not str(expr).strip():
            return []
        try:
            return node.xpath(expr)
        except etree.XPathEvalError as e:
            raise ParserConfigError(
                f"Invalid XPath expression: {expr}"
            ) from e
