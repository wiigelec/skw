#!/usr/bin/env python3
"""
Stage 1 – Generate Dependency Files (Recursive)
-----------------------------------------------
Reads YAML package metadata and writes normalized `.dep` files
for all packages reachable from a given root package.

Usage:
    python skwdepsolver.py --input ./packages --output ./out --root systemd
"""

from pathlib import Path
import yaml
import argparse

class SKWDepSolver:
    def __init__(self, input_dir: Path, output_dir: Path, root_package: str):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.deps_dir = self.output_dir / "deps"
        self.root_package = root_package
        self.pkg_data = {}
        self.visited = set()

        # ensure output dir exists
        self.deps_dir.mkdir(parents=True, exist_ok=True)

        # preload YAML metadata
        self._load_yaml_packages()

    def _load_yaml_packages(self):
        """Load all YAML metadata into memory."""
        for yaml_file in self.input_dir.glob("*.yaml"):
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if "name" in data:
                self.pkg_data[data["name"]] = data

    def _extract_dependencies(self, dependencies: dict) -> list[str]:
        """Convert dependency dict into normalized lines for .dep file."""
        dep_lines = []

        # Map dependency categories to weights
        weights = {
            "required": 1,
            "recommended": 2,
            "optional": 3,
            "external": 4,
        }

        # Map subkeys to qualifiers
        qualifiers = {
            "first": "f",
            "before": "b",
            "after": "a",
        }

        for dep_type, dep_value in dependencies.items():
            weight = weights.get(dep_type)
            if weight is None:
                continue

            if isinstance(dep_value, dict):
                for qkey, qval in dep_value.items():
                    if qval:
                        dep_lines.append(f"{weight} {qualifiers[qkey]} {qval}")
            elif isinstance(dep_value, list):
                for item in dep_value:
                    dep_lines.append(f"{weight} b {item}")
            elif isinstance(dep_value, str) and dep_value.strip():
                # external may be a URL; derive a simple name
                name = dep_value.split("/")[-1] if "://" in dep_value else dep_value
                dep_lines.append(f"{weight} b {name}")

        return dep_lines

    def _write_dep_file(self, pkg_name: str, dependencies: dict):
        """Write a .dep file for a package."""
        dep_lines = self._extract_dependencies(dependencies)
        dep_file_path = self.deps_dir / f"{pkg_name}.dep"
        with open(dep_file_path, "w", encoding="utf-8") as dep_file:
            dep_file.write("\n".join(dep_lines) + "\n")
        print(f"[OK] Generated {dep_file_path.name}")

    def _traverse_dependencies(self, pkg_name: str):
        """Recursively traverse dependencies and generate .dep files."""
        if pkg_name in self.visited:
            return
        self.visited.add(pkg_name)

        pkg_data = self.pkg_data.get(pkg_name)
        if not pkg_data:
            print(f"[WARN] Missing metadata for {pkg_name}")
            return

        dependencies = pkg_data.get("dependencies", {})
        self._write_dep_file(pkg_name, dependencies)

        # Extract dependency names for recursion
        dep_names = set()
        for dep_type, dep_value in dependencies.items():
            if isinstance(dep_value, dict):
                for v in dep_value.values():
                    if v:
                        dep_names.add(v)
            elif isinstance(dep_value, list):
                dep_names.update(dep_value)
            elif isinstance(dep_value, str) and dep_value.strip():
                name = dep_value.split("/")[-1] if "://" in dep_value else dep_value
                dep_names.add(name)

        for dep in dep_names:
            if dep in self.pkg_data:
                self._traverse_dependencies(dep)

    def run(self):
        if not self.root_package:
            raise ValueError("Root package must be specified with --root")
        print(f"[*] Starting dependency traversal from root: {self.root_package}")
        self._traverse_dependencies(self.root_package)


def main():
    parser = argparse.ArgumentParser(description="SKWDepSolver - Stage 1 Recursive Dependency Generator")
    parser.add_argument("--input", required=True, help="Directory containing YAML package files")
    parser.add_argument("--output", required=True, help="Output directory for .dep files")
    parser.add_argument("--root", required=True, help="Root package name to start dependency traversal")
    args = parser.parse_args()

    solver = SKWDepSolver(args.input, args.output, args.root)
    solver.run()


if __name__ == "__main__":
    main()
