import os
import sys
import json
import tomllib
from lxml import etree

class SKWParser:
    def __init__(self, build_dir, profiles_dir, book, profile):
        self.build_dir = build_dir
        self.profiles_dir = profiles_dir
        self.book = book
        self.profile = profile

        # parser.toml lives in profiles repo
        self.config_path = os.path.join(
            profiles_dir, book, profile, "parser.toml"
        )

        if not os.path.exists(self.config_path):
            sys.exit(f"Error: parser.toml not found for book '{book}' profile '{profile}'.")

        with open(self.config_path, "rb") as f:
            self.cfg = tomllib.load(f)

    def run(self):
        xml_path = self._substitute(self.cfg["main"]["xml_path"])
        output_file = self.cfg["main"]["output_file"]

        if not os.path.exists(xml_path):
            sys.exit(f"Error: XML book not found at {xml_path}. Did you run install-book?")

        # Load XML
        tree = etree.parse(xml_path)
        results = []

        # --- Normal book parsing ---
        chapter_xpath = self.cfg["xpaths"]["chapter_id"]
        section_xpath = self.cfg["xpaths"]["section_id"]

        chapters = tree.xpath(chapter_xpath)
        for chap in chapters:
            chap_id = chap.get("id")
            if not self._filter_ok(chap_id, self.cfg.get("chapter_filters", {})):
                continue

            sections = chap.xpath(section_xpath)
            for sec in sections:
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

                # Sources
                src_title_expr = self._expand_xpath(
                    self._get_xpath_expr(sec_id, chap_id, "source_titles"), context
                )
                src_url_expr = self._expand_xpath(
                    self._get_xpath_expr(sec_id, chap_id, "source_urls"), context
                )
                src_cksum_expr = self._expand_xpath(
                    self._get_xpath_expr(sec_id, chap_id, "source_checksums"), context
                )

                sources = {
                    "titles": sec.xpath(src_title_expr) if src_title_expr else [],
                    "urls": sec.xpath(src_url_expr) if src_url_expr else [],
                    "checksums": sec.xpath(src_cksum_expr) if src_cksum_expr else [],
                }

                deps_expr = self._get_xpath_expr(sec_id, chap_id, "dependencies")
                deps = sec.xpath(deps_expr) if deps_expr else []

                # Build instructions
                build_instructions = []
                build_inst_expr = self._get_xpath_expr(sec_id, chap_id, "build_instructions")
                if build_inst_expr:
                    for node in sec.xpath(build_inst_expr):
                        cmd = "".join(node.itertext()).strip()
                        if cmd:
                            build_instructions.append(cmd)

                entry = {
                    "source_book": self.book,
                    "chapter_id": chap_id,
                    "section_id": sec_id,
                    "package_name": pkg_name,
                    "package_version": pkg_ver,
                    "sources": sources,
                    "dependencies": deps,
                    "build_instructions": build_instructions,
                }
                results.append(entry)

        # --- Custom code packages ---
        custom_cfgs = self.cfg.get("custom_code", {}).get("configs", [])
        for cfg_file in custom_cfgs:
            cfg_path = os.path.join(self.profiles_dir, self.book, self.profile, cfg_file)
            if not os.path.exists(cfg_path):
                sys.exit(f"Custom config not found: {cfg_path}")

            with open(cfg_path, "rb") as f:
                custom_cfg = tomllib.load(f)

            for pkg in custom_cfg.get("custom_packages", []):
                name = pkg.get("name")
                version = pkg.get("version", "")
                section_id = pkg.get("section_id", f"custom-{name}")
                chapter_id = pkg.get("chapter_id", f"custom-{name}")

                build_instructions = []

                # Inline commands
                for cmd in pkg.get("commands", []):
                    build_instructions.append(cmd)

                # XPath commands
                xpath_cmds = pkg.get("xpath_commands", [])
                if isinstance(xpath_cmds, str):
                    xpath_cmds = [xpath_cmds]

                for expr in xpath_cmds:
                    nodes = tree.xpath(expr)
                    for node in nodes:
                        cmd = "".join(node.itertext()).strip()
                        if cmd:
                            build_instructions.append(cmd)

                entry = {
                    "source_book": self.book,
                    "chapter_id": chapter_id,
                    "section_id": section_id,
                    "package_name": name,
                    "package_version": version,
                    "sources": {"titles": [], "urls": [], "checksums": []},
                    "dependencies": [],
                    "build_instructions": build_instructions,
                }
                results.append(entry)

        # --- Write output ---
        profile_parser_dir = os.path.join(self.build_dir, "parser", self.book, self.profile)
        os.makedirs(profile_parser_dir, exist_ok=True)
        output_path = os.path.join(profile_parser_dir, output_file)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        print(f"Parser complete. Output written to {output_path}")

    # --- Helpers ---
    def _get_xpath_expr(self, sec_id, chap_id, key):
        if sec_id in self.cfg and "xpaths" in self.cfg[sec_id]:
            if key in self.cfg[sec_id]["xpaths"]:
                return self.cfg[sec_id]["xpaths"][key]
        if chap_id in self.cfg and "xpaths" in self.cfg[chap_id]:
            if key in self.cfg[chap_id]["xpaths"]:
                return self.cfg[chap_id]["xpaths"][key]
        return self.cfg["xpaths"].get(key, None)

    def _expand_xpath(self, expr, context):
        if not expr:
            return None
        for key, val in context.items():
            expr = expr.replace(f"${{{key}}}", val)
        return expr

    def _filter_ok(self, value, filters):
        inc = filters.get("include", [])
        exc = filters.get("exclude", [])
        if inc and value not in inc:
            return False
        if exc and value in exc:
            return False
        return True

    def _xpath_or_none(self, node, expr):
        if not expr:
            return None
        result = node.xpath(expr)
        if not result:
            return None
        return result[0] if isinstance(result[0], str) else str(result[0])

    def _substitute(self, value: str) -> str:
        substitutions = {
            "${book}": self.book,
            "${profile}": self.profile,
            "${build_dir}": self.build_dir,
        }
        for key, val in substitutions.items():
            value = value.replace(key, val)
        return value

