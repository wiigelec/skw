#!/usr/bin/env python3
"""
Stage 1 – Generate Dependency Files
-----------------------------------
Reads YAML package metadata and writes normalized `.dep` files.

Usage:
    python skwdepsolver.py --input ./packages --output ./out --stage 1
"""

from pathlib import Path
import yaml
import argparse

class SKWDepSolver:
    def __init__(self, input_dir: Path, output_dir: Path, stage: str = "1"):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.deps_dir = self.output_dir / "deps"
        self.stage = stage

        # ensure output dir exists
        self.deps_dir.mkdir(parents=True, exist_ok=True)

    # ---------- Stage 1 ----------
    def generate_dependency_files(self):
        """Parse YAML metadata and create .dep files."""
        for yaml_file in self.input_dir.glob("*.yaml"):
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            pkg_name = data.get("name")
            dependencies = data.get("dependencies", {})
            dep_lines = self._extract_dependencies(dependencies)

            dep_file_path = self.deps_dir / f"{pkg_name}.dep"
            with open(dep_file_path, "w", encoding="utf-8") as dep_file:
                dep_file.write("\n".join(dep_lines) + "\n")

            print(f"[OK] Generated {dep_file_path}")

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
                # expected: { first: <pkg>, before: <pkg>, after: <pkg> }
                for qkey, qval in dep_value.items():
                    if qval:
                        dep_lines.append(f"{weight} {qualifiers[qkey]} {qval}")

            elif isinstance(dep_value, list):
                for item in dep_value:
                    dep_lines.append(f"{weight} b {item}")

            elif isinstance(dep_value, str) and dep_value.strip():
                # external may be a URL; if so, derive a simple name
                name = dep_value.split("/")[-1] if "://" in dep_value else dep_value
                dep_lines.append(f"{weight} b {name}")

        return dep_lines

    # ---------- CLI Entry ----------
    def run(self):
        if self.stage in ("1", "all"):
            self.generate_dependency_files()


def main():
    parser = argparse.ArgumentParser(description="SKWDepSolver - Stage 1 Dependency Generator")
    parser.add_argument("--input", required=True, help="Directory containing YAML package files")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--stage", choices=["1", "all"], default="1", help="Stage to run")
    args = parser.parse_args()

    solver = SKWDepSolver(args.input, args.output, args.stage)
    solver.run()


if __name__ == "__main__":
    main()
