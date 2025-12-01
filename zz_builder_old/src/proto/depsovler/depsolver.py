#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import yaml
import toml
import json
import argparse
import sys


class DependencySolver:
    """
    Stage 1: Recursive dependency structure builder.
    Parses package YAMLs, applies alias resolution, and recursively builds dependency trees.
    """

    def __init__(self, target: str, yaml_dir: Path, alias_file: Path, include_classes: list[str]):
        self.target = target
        self.yaml_dir = Path(yaml_dir)
        self.alias_file = Path(alias_file)
        self.include_classes = include_classes
        self.alias_map = self._load_aliases()
        self.dependency_tree: dict[str, dict] = {}

    # ---------------------------
    # Alias & YAML loading
    # ---------------------------
    def _load_aliases(self) -> dict[str, str]:
        """Load alias mappings from a TOML file."""
        if not self.alias_file.exists():
            print(f"[WARN] Alias file not found: {self.alias_file}")
            return {}
        with open(self.alias_file, "r") as f:
            data = toml.load(f)
        return data.get("aliases", {})

    def _resolve_yaml_path(self, dep: str) -> Path:
        """
        Resolve dependency name to YAML file path using base-name heuristic and alias map.
        Rules:
          1. Match base name (strip everything after last '-')
          2. If ambiguous -> hard error
          3. If not found -> use alias map
          4. If still not found -> hard error
        """
        candidates = []
        for f in self.yaml_dir.glob("*.yaml"):
            parts = f.stem.split("-")
            base = "-".join(parts[:-1]) if len(parts) > 1 else f.stem
            if base == dep:
                candidates.append(f)

        if len(candidates) > 1:
            raise RuntimeError(f"Multiple YAML files match dependency '{dep}': {[c.name for c in candidates]}")
        if len(candidates) == 1:
            return candidates[0]

        if dep in self.alias_map:
            alias_name = self.alias_map[dep]
            yaml_path = self.yaml_dir / f"{alias_name}.yaml"
            if not yaml_path.exists():
                raise FileNotFoundError(f"Alias '{dep}' points to missing file '{yaml_path.name}'")
            return yaml_path

        raise FileNotFoundError(f"No YAML found for dependency '{dep}'")

    # ---------------------------
    # YAML and dependency parsing
    # ---------------------------
    def _parse_yaml(self, yaml_path: Path) -> dict:
        with open(yaml_path, "r") as f:
            return yaml.safe_load(f) or {}

    def _normalize_names(self, entry: dict) -> list[str]:
        if not entry or entry == "" or entry == {"name": ""}:
            return []
        names = entry.get("name", [])
        if isinstance(names, str):
            return [names]
        return [n for n in names if n]

    # ---------------------------
    # Recursive dependency resolver
    # ---------------------------
    def _collect_dependencies(
        self, package: str, visited: set[str] | None = None, stack: list[str] | None = None
    ) -> dict:
        if visited is None:
            visited = set()
        if stack is None:
            stack = []

        if package in stack:
            return {"_circular_ref": package}

        stack.append(package)

        try:
            yaml_path = self._resolve_yaml_path(package)
        except (FileNotFoundError, RuntimeError) as e:
            return {"_error": str(e)}

        pkg_data = self._parse_yaml(yaml_path)
        deps = pkg_data.get("dependencies", {})
        result = {}

        for key, value in deps.items():
            for cls in self.include_classes:
                if key.startswith(cls):
                    dep_list = self._normalize_names(value)
                    if dep_list:
                        phase = key.split("_", 1)[1] if "_" in key else "unspecified"
                        result[f"{cls}_{phase}"] = {}
                        for dep in dep_list:
                            result[f"{cls}_{phase}"][dep] = self._collect_dependencies(dep, visited, stack.copy())

        stack.pop()
        visited.add(package)
        return result

    # ---------------------------
    # Public API
    # ---------------------------
    def build_tree(self) -> dict:
        """Public method to trigger dependency resolution."""
        print(f"[INFO] Building dependency tree for target: {self.target}")
        self.dependency_tree = self._collect_dependencies(self.target)
        return self.dependency_tree

    def print_tree(self):
        """Pretty-print the dependency tree for inspection."""
        print(json.dumps(self.dependency_tree, indent=2))


# ---------------------------
# CLI Entrypoint
# ---------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Dependency Solver — Build a recursive dependency tree from YAML package definitions."
    )
    parser.add_argument("--target", required=True, help="Target package to resolve (e.g., systemd)")
    parser.add_argument("--yaml-dir", required=True, type=Path, help="Directory containing package YAML files")
    parser.add_argument("--alias-file", required=True, type=Path, help="Path to TOML alias mapping file")
    parser.add_argument(
        "--classes",
        nargs="+",
        default=["required", "recommended"],
        help="Dependency classes to include (default: required recommended)",
    )
    parser.add_argument("--output", type=Path, help="Optional path to save output JSON file")

    args = parser.parse_args()

    try:
        solver = DependencySolver(args.target, args.yaml_dir, args.alias_file, args.classes)
        tree = solver.build_tree()

        if args.output:
            with open(args.output, "w") as f:
                json.dump(tree, f, indent=2)
            print(f"[INFO] Dependency tree saved to: {args.output}")
        else:
            solver.print_tree()

    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
