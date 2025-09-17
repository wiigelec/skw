import os
import sys
import json
import tomllib
from lxml import etree

class Parser:
    def __init__(self, build_dir, book, profile):
        self.build_dir = build_dir
        self.book = book
        self.profile = profile
        self.config_path = os.path.join(
            build_dir, "books", book, "config", profile, "parser.toml"
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

                build_instructions = []
                userinput_nodes = sec.xpath(self.cfg["xpaths"]["build_instructions"]) if self.cfg["xpaths"]["build_instructions"] else []
                for userinput_node in userinput_nodes:
                    full_command = "".join(userinput_node.itertext()).strip()

                    if full_command:
                        build_instructions.append(full_command)

                entry = {
                    "source_book": self.book,
                    "chapter_id": chap_id,
                    "section_id": sec_id,
                    "package_name": self._xpath_or_none(sec, self.cfg["xpaths"]["package_name"]),
                    "package_version": self._xpath_or_none(sec, self.cfg["xpaths"]["package_version"]),
                    "sources": {
                        "titles": sec.xpath(self.cfg["xpaths"].get("source_titles", "")) if self.cfg["xpaths"].get("source_titles") else [],
                        "urls": sec.xpath(self.cfg["xpaths"].get("source_urls", "")) if self.cfg["xpaths"].get("source_urls") else [],
                        "checksums": sec.xpath(self.cfg["xpaths"].get("source_checksums", "")) if self.cfg["xpaths"].get("source_checksums") else [],
                    },
                    "dependencies": sec.xpath(self.cfg["xpaths"]["dependencies"]) if self.cfg["xpaths"]["dependencies"] else [],
                    "build_instructions":build_instructions
                }
                results.append(entry)

        # Output directory
        profile_parser_dir = os.path.join(self.build_dir, "parser", self.profile)
        os.makedirs(profile_parser_dir, exist_ok=True)
        output_path = os.path.join(profile_parser_dir, output_file)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        print(f"Parser complete. Output written to {output_path}")

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
        """Replace placeholders like ${book}, ${profile}, ${build_dir}"""
        substitutions = {
            "${book}": self.book,
            "${profile}": self.profile,
            "${build_dir}": self.build_dir,
        }
        for key, val in substitutions.items():
            value = value.replace(key, val)
        return value


