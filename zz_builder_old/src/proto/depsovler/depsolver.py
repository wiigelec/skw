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
    Stage 1: Recursive dependency structure builder (strict mode, case-insensitive, safe alias skipping).
    Parses package YAMLs, applies alias resolution, and recursively builds dependency trees.
    """

    def __init__(self, target: str, yaml_dir: Path, alias_file: Path, include_classes: list[str]):
        self.target = target.lower()
        self.yaml_dir = Path(yaml_dir)
        self.alias_file = Path(alias_file)
        self.include_classes = include_classes
        self.alias_map = self._load_aliases()
        self.dependency_tree: dict[str, dict] = {}

    # ---------------------------
    # Alias & YAML loading
    # ---------------------------
    def _load_aliases(self) -> dict[str, str]:
        """Load alias mappings from a TOML file (keys converted to lowercase)."""
        if not self.alias_file.exists():
            print(f"[ERROR] Alias file not found: {self.alias_file}")
            sys.exit(1)

        with open(self.alias_file, "r") as f:
            data = toml.load(f)

        aliases = data.get("aliases", {})
        # Normalize keys to lowercase and skip empty aliases
        valid_aliases = {}
        for k, v in aliases.items():
            if isinstance(v, str) and v.strip():
                valid_aliases[k.lower()] = v
            else:
                print(f"[WARN] Skipping empty alias entry for '{k}'")

        return valid_aliases

    def _resolve_yaml_path(self, dep: str) -> Path:
        """
        Resolve dependency name to YAML file path using base-name heuristic and alias map.
        Rules:
          1. Match base name (strip everything after last '-')
          2. Convert all names to lowercase before comparing
          3. If ambiguous -> hard error
          4. If not found -> use alias map
          5. If alias empty -> warn and skip
          6. If still not found -> hard error and exit
        """
        dep = dep.lower()
        candidates = []

        for f in self.yaml_dir.glob("*.yaml"):
            parts = f.stem.split("-")
            base = "-".join(parts[:-1]) if len(parts) > 1 else f.stem
            if base.lower() == dep:
                candidates.append(f)

        if len(candidates) > 1:
            print(f"[ERROR] Multiple YAML files match dependency '{dep}': {[c.name for c in candidates]}")
            sys.exit(1)
        if len(candidates) == 1:
            return candidates[0]

        if dep in self.alias_map:
            alias_name = self.alias_map[dep]
            if not alias_name.strip():
                print(f"[WARN] Alias for '{dep}' is empty; skipping alias lookup.")
            else:
                yaml_path = self.yaml_dir / f"{alias_name}.yaml"
                if not yaml_path.exists():
                    print(f"[ERROR] Alias '{dep}' points to missing file '{yaml_path.name}'")
                    sys.exit(1)
                return yaml_path

        print(f"[ERROR] No YAML found for dependency '{dep}'")
        sys.exit(1)

    # ---------------------------
    # YAML and dependency parsing
    # ---------------------------
    def _parse_yaml(self, yaml_path: Path) -> dict:
        with open(yaml_path, "r") as f:
            return yaml.safe_load(f) or {}

    def _normalize_names(self, entry: dict) -> list[str]:
        """Normalize dependency entries to lowercase list."""
        if not entry or entry == "" or entry == {"name": ""}:
            return []
        names = entry.get("name", [])
        if isinstance(names, str):
            return [names.lower()]
        return [n.lower() for n in names if n]

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

        package = package.lower()

        if package in stack:
            return {"_circular_ref": package}

        stack.append(package)

        yaml_path = self._resolve_yaml_path(package)
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
        description="Dependency Solver — Strict mode, case-insensitive, safe alias skipping."
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

    solver = DependencySolver(args.target, args.yaml_dir, args.alias_file, args.classes)
    tree = solver.build_tree()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(tree, f, indent=2)
        print(f"[INFO] Dependency tree saved to: {args.output}")
    else:
        solver.print_tree()


if __name__ == "__main__":
    main()
