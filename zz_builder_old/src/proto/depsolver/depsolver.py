#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import yaml
import toml
import json
import argparse
import sys
from collections import defaultdict


class DependencySolver:
    """
    DependencySolver — Stage 1 strict mode with recursive 5-phase dependency support.
    Honors --classes filters (e.g. required, recommended).
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
        normalized = {}
        for k, v in aliases.items():
            key = k.lower()
            if isinstance(v, str):
                normalized[key] = v.strip()
            else:
                normalized[key] = ""
                print(f"[WARN] Alias for '{k}' is not a string; treating as blank.")
        return normalized

    def _resolve_yaml_path(self, dep: str) -> Path | None:
        """Resolve dependency name to YAML file path."""
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
            alias_value = self.alias_map[dep]
            if not alias_value:
                print(f"[WARN] Alias for '{dep}' is empty; skipping dependency.")
                return None
            yaml_path = self.yaml_dir / f"{alias_value}.yaml"
            if not yaml_path.exists():
                print(f"[ERROR] Alias '{dep}' points to missing file '{yaml_path.name}'")
                sys.exit(1)
            return yaml_path

        print(f"[ERROR] No YAML or alias found for dependency '{dep}'")
        sys.exit(1)

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
    # Normal dependency resolver (strict mode)
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
        if yaml_path is None:
            stack.pop()
            return {"_warn": f"Skipped due to blank alias for {package}"}

        pkg_data = self._parse_yaml(yaml_path)
        deps = pkg_data.get("dependencies", {})
        result = {}

        for key, value in deps.items():
            prefix = key.split("_", 1)[0]
            if prefix not in self.include_classes:
                continue
            dep_list = self._normalize_names(value)
            if dep_list:
                phase = key.split("_", 1)[1] if "_" in key else "unspecified"
                result[f"{prefix}_{phase}"] = {}
                for dep in dep_list:
                    result[f"{prefix}_{phase}"][dep] = self._collect_dependencies(dep, visited, stack.copy())

        stack.pop()
        visited.add(package)
        return result

    def build_tree(self) -> dict:
        print(f"[INFO] Building dependency tree for target: {self.target}")
        self.dependency_tree = self._collect_dependencies(self.target)
        return self.dependency_tree

    def print_tree(self):
        print(json.dumps(self.dependency_tree, indent=2))

    # ---------------------------
    # Recursive full-phase dependency builder (honors --classes)
    # ---------------------------
    def _expand_phase_tree(self, pkg: str, visited=None):
        """
        Recursively expand a package into a full 5-phase dependency structure:
        bootstrap1_pkg, before_pkg, target_pkg, bootstrap2_pkg, after_pkg
        Only includes dependency classes listed in self.include_classes.
        """
        if visited is None:
            visited = set()

        pkg = pkg.lower()

        if pkg in visited:
            return {f"target_{pkg}": pkg, "_circular_ref": pkg}

        visited.add(pkg)
        yaml_path = self._resolve_yaml_path(pkg)
        if not yaml_path:
            return {f"target_{pkg}": pkg, "_warn": f"No YAML found for {pkg}"}

        data = self._parse_yaml(yaml_path)
        deps = data.get("dependencies", {})

        tree = {
            f"bootstrap1_{pkg}": [],
            f"before_{pkg}": {},
            f"target_{pkg}": pkg,
            f"bootstrap2_{pkg}": [],
            f"after_{pkg}": {},
        }

        for key, entry in deps.items():
            prefix = key.split("_", 1)[0]
            if prefix not in self.include_classes:
                continue

            # Bootstrap deps
            if key.endswith("_first"):
                dep_list = self._normalize_names(entry)
                for dep in dep_list:
                    subtree = self._expand_phase_tree(dep, visited)
                    tree[f"bootstrap1_{pkg}"].append(subtree)
                    tree[f"bootstrap2_{pkg}"].append(subtree)

            # Buildtime deps
            elif key.endswith("_before"):
                dep_list = self._normalize_names(entry)
                for dep in dep_list:
                    tree[f"before_{pkg}"][dep] = self._expand_phase_tree(dep, visited)

            # Runtime deps
            elif key.endswith("_after"):
                dep_list = self._normalize_names(entry)
                for dep in dep_list:
                    tree[f"after_{pkg}"][dep] = self._expand_phase_tree(dep, visited)

        return tree

    def build_full_phase_tree(self):
        """Return the fully recursive 5-phase dependency tree."""
        return self._expand_phase_tree(self.target)

    def print_full_phase_tree(self):
        tree = self.build_full_phase_tree()
        print(json.dumps(tree, indent=2))


# ---------------------------
# CLI Entrypoint
# ---------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Dependency Solver — strict mode with optional recursive 5-phase tree."
    )
    parser.add_argument("--target", required=True, help="Target package to resolve (e.g., mesa)")
    parser.add_argument("--yaml-dir", required=True, type=Path, help="Directory containing package YAML files")
    parser.add_argument("--alias-file", required=True, type=Path, help="Path to TOML alias mapping file")
    parser.add_argument(
        "--classes",
        nargs="+",
        default=["required", "recommended"],
        help="Dependency classes to include (default: required recommended)",
    )
    parser.add_argument("--output", type=Path, help="Optional path to save output JSON file")
    parser.add_argument("--full-phase-tree", action="store_true", help="Generate recursive full 5-phase dependency tree")

    args = parser.parse_args()

    solver = DependencySolver(args.target, args.yaml_dir, args.alias_file, args.classes)

    if args.full_phase_tree:
        tree = solver.build_full_phase_tree()
        if args.output:
            with open(args.output, "w") as f:
                json.dump(tree, f, indent=2)
            print(f"[INFO] Full-phase dependency tree saved to: {args.output}")
        else:
            solver.print_full_phase_tree()
    else:
        tree = solver.build_tree()
        if args.output:
            with open(args.output, "w") as f:
                json.dump(tree, f, indent=2)
            print(f"[INFO] Dependency tree saved to: {args.output}")
        else:
            solver.print_tree()


if __name__ == "__main__":
    main()
