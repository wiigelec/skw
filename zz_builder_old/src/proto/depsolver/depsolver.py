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
    # Strict dependency resolver
    # ---------------------------
    def _collect_dependencies(self, package: str, visited: set[str] | None = None, stack: list[str] | None = None) -> dict:
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
    # Full-phase builder
    # ---------------------------
    def _expand_phase_tree(self, pkg: str, visited=None):
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
            dep_list = self._normalize_names(entry)
            if key.endswith("_first"):
                for dep in dep_list:
                    subtree = self._expand_phase_tree(dep, visited)
                    tree[f"bootstrap1_{pkg}"].append(subtree)
                    tree[f"bootstrap2_{pkg}"].append(subtree)
            elif key.endswith("_before"):
                for dep in dep_list:
                    tree[f"before_{pkg}"][dep] = self._expand_phase_tree(dep, visited)
            elif key.endswith("_after"):
                for dep in dep_list:
                    tree[f"after_{pkg}"][dep] = self._expand_phase_tree(dep, visited)
        return tree

    def build_full_phase_tree(self):
        return self._expand_phase_tree(self.target)

    def print_full_phase_tree(self):
        tree = self.build_full_phase_tree()
        print(json.dumps(tree, indent=2))

    # ---------------------------
    # Flatten (v5 logic integrated)
    # ---------------------------
    def flatten_phases(self, node, built_so_far=None, first_seen=None, target_pkg=None):
        if built_so_far is None:
            built_so_far = set()
        if first_seen is None:
            first_seen = set()
        if target_pkg is None:
            target_pkg = self.target

        order = {
            "bootstrap_pass1": [],
            "buildtime": [],
            "target": [],
            "bootstrap_pass2": [],
            "runtime": [],
        }
        bootstrap2_set = set()

        if not isinstance(node, dict):
            return order

        for key, value in node.items():
            if key.startswith("bootstrap1_"):
                for dep in value:
                    if isinstance(dep, dict):
                        dep_name = next(iter(dep.values())) if isinstance(next(iter(dep.values())), str) else None
                        if not dep_name:
                            dep_key = next(iter(dep.keys()), None)
                            dep_name = dep_key.split("_", 1)[-1] if dep_key else None
                        if dep_name:
                            sub = self.flatten_phases(dep, built_so_far, first_seen, target_pkg)
                            order["bootstrap_pass1"].extend(sub["bootstrap_pass1"])
                            order["bootstrap_pass1"].extend(sub["buildtime"])
                            if dep_name not in first_seen:
                                order["bootstrap_pass1"].append(dep_name)
                                first_seen.add(dep_name)
                                built_so_far.add(dep_name)

            elif key.startswith("bootstrap2_"):
                for dep in value:
                    if isinstance(dep, dict):
                        dep_name = next(iter(dep.values())) if isinstance(next(iter(dep.values())), str) else None
                        if not dep_name:
                            dep_key = next(iter(dep.keys()), None)
                            dep_name = dep_key.split("_", 1)[-1] if dep_key else None
                        if dep_name:
                            order["bootstrap_pass2"].append(dep_name)
                            bootstrap2_set.add(dep_name)

            elif key.startswith("before_"):
                for dep, subnode in value.items():
                    if dep not in built_so_far:
                        built_so_far.add(dep)
                        sub = self.flatten_phases(subnode, built_so_far, first_seen, target_pkg)
                        for k in order:
                            order[k].extend(sub[k])
                        order["buildtime"].append(dep)

            elif key.startswith("target_"):
                pkg = value
                if pkg == target_pkg:
                    order["target"].append(pkg)
                    built_so_far.add(pkg)
                elif pkg not in built_so_far:
                    built_so_far.add(pkg)
                    order["buildtime"].append(pkg)

            elif key.startswith("after_"):
                for dep, subnode in value.items():
                    if dep not in built_so_far:
                        built_so_far.add(dep)
                        sub = self.flatten_phases(subnode, built_so_far, first_seen, target_pkg)
                        for k in order:
                            order[k].extend(sub[k])
                        order["runtime"].append(dep)

        for k in order:
            seen = set()
            order[k] = [x for x in order[k] if x not in seen and not seen.add(x)]
        order["buildtime"] = [p for p in order["buildtime"] if p not in bootstrap2_set]
        return order


# ---------------------------
# CLI Entrypoint
# ---------------------------
def main():
    parser = argparse.ArgumentParser(description="Dependency Solver — strict mode with optional recursive 5-phase tree.")
    parser.add_argument("--target", required=True, help="Target package to resolve (e.g., mesa)")
    parser.add_argument("--yaml-dir", required=True, type=Path, help="Directory containing YAML package files")
    parser.add_argument("--alias-file", required=True, type=Path, help="Path to TOML alias mapping file")
    parser.add_argument("--classes", nargs="+", default=["required", "recommended"], help="Dependency classes to include")
    parser.add_argument("--output", type=Path, help="Optional path to save output JSON file")
    parser.add_argument("--full-phase-tree", action="store_true", help="Generate recursive full 5-phase dependency tree")
    parser.add_argument("--flat-phase-tree", action="store_true", help="Generate final flat ordered build list")

    args = parser.parse_args()
    solver = DependencySolver(args.target, args.yaml_dir, args.alias_file, args.classes)

    if args.full_phase_tree or args.flat_phase_tree:
        tree = solver.build_full_phase_tree()
        if args.output:
            with open(args.output, "w") as f:
                json.dump(tree, f, indent=2)
            print(f"[INFO] Full-phase dependency tree saved to: {args.output}")

        if args.flat_phase_tree:
            result = solver.flatten_phases(tree)
            print("\n===== FINAL ORDERED BUILD LIST =====\n")
            for phase in ["bootstrap_pass1", "buildtime", "target", "bootstrap_pass2", "runtime"]:
                print(f"[{phase.upper()}]")
                print(" ".join(result[phase]) or "(none)")
                print()
            sys.exit(0)

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
