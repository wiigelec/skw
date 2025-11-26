#!/usr/bin/env python3
"""
DepSolver - Unified Dependency Graph Generator (Steps 2 + 3)
-------------------------------------------------------------
Recreates the BLFS generate_deps() and generate_subgraph() logic
using YAML package metadata and TOML alias mapping.
"""

import os
import sys
import glob
import yaml
import toml
import argparse


class DepSolver:
    PRIORITY_MAP = {
        "required": 1,
        "recommended": 2,
        "optional": 3,
        "external": 4
    }

    def __init__(self, dep_dir: str, dep_level: int, package_dir: str, config_file: str):
        self.dep_dir = os.path.abspath(dep_dir)
        self.package_dir = os.path.abspath(package_dir)
        self.dep_level = int(dep_level)
        os.makedirs(self.dep_dir, exist_ok=True)

        self.aliases = self._load_aliases(config_file)
        self.visited = set()

    # -------------------------------------------------------
    def _load_aliases(self, config_path: str):
        if not os.path.exists(config_path):
            print(f"[ERROR] Config file not found: {config_path}")
            sys.exit(1)
        cfg = toml.load(config_path)
        return cfg.get("package_aliases", {})

    # -------------------------------------------------------
    def _resolve_package_name(self, name: str):
        """Apply alias mappings if defined."""
        return self.aliases.get(name, name)

    # -------------------------------------------------------
    def _find_yaml_for_package(self, package: str):
        """Find <package>-<version>.yaml file, using alias if necessary."""
        pkg_alias = self._resolve_package_name(package)
        pattern = os.path.join(self.package_dir, f"{pkg_alias}-*.yaml")
        files = glob.glob(pattern)
        if not files:
            print(f"[ERROR] No YAML file found for package '{package}' (alias: '{pkg_alias}')")
            sys.exit(1)
        # Select the lexicographically latest (e.g., highest version)
        return sorted(files)[-1]

    # -------------------------------------------------------
    def _read_yaml_deps(self, yaml_path: str):
        """
        Parse YAML and return list of (priority, qualifier_code, dep_name).
        Supports structure:
          dependencies:
            required_before: { name: "glibc" }
            optional_before: { name: ["curl", "git"] }
        """
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        deps = []
        dep_data = data.get("dependencies", {})

        if not isinstance(dep_data, dict):
            print(f"[ERROR] Invalid dependencies structure in {yaml_path}. Expected a mapping.")
            sys.exit(1)

        for key, obj in dep_data.items():
            key = key.lower().strip()
            if not isinstance(obj, dict) or "name" not in obj:
                continue

            names = obj["name"]
            if not names:
                continue  # empty, skip

            # Normalize names to a list
            if isinstance(names, str):
                names = [names]
            elif not isinstance(names, list):
                print(f"[WARN] Unexpected type for {key} in {yaml_path}: {type(names).__name__}")
                continue

            # Extract type and qualifier
            dep_type = None
            qualifier = None
            for t in ("required", "recommended", "optional", "external"):
                if key.startswith(t):
                    dep_type = t
                    rest = key[len(t):].lstrip("_")
                    qualifier = rest or "before"
                    break

            if dep_type is None:
                print(f"[WARN] Could not determine dependency type for '{key}' in {yaml_path}")
                continue

            # Determine priority and qualifier code
            priority = self.PRIORITY_MAP.get(dep_type, 1)
            qual_map = {
                "before": "b",
                "after": "a",
                "first": "f",
                "external": "b"
            }
            q_code = qual_map.get(qualifier, "b")

            # Special case: optional_external → priority 4, qualifier b
            if key == "optional_external":
                priority = 4
                q_code = "b"

            # Add each dependency package
            for pkg in names:
                pkg = str(pkg).strip()
                if not pkg:
                    continue
                deps.append((priority, q_code, pkg))

        return deps

    # -------------------------------------------------------
    def generate_deps(self, packages: list[str]):
        """
        Step 2 — Initialize dependency graph root.
        Creates 'root.dep' with one line per target: '1 b <package>'
        """
        dep_glob = os.path.join(self.dep_dir, "*")
        for f in glob.glob(dep_glob):
            if f.endswith(".dep") or f.endswith(".tree"):
                os.remove(f)
        root_path = os.path.join(self.dep_dir, "root.dep")
        with open(root_path, "w") as root:
            for pkg in packages:
                pkg = pkg.strip()
                if pkg:
                    root.write(f"1 b {pkg}\n")
        print(f"[OK] Created {root_path}")
        return root_path

    # -------------------------------------------------------
    def generate_subgraph(self, dep_file: str, weight: int, depth: int, qualifier: str):
        """
        Step 3 — Recursively expand dependency graph from YAML metadata.
        """
        dep_path = os.path.join(self.dep_dir, dep_file)
        if not os.path.exists(dep_path):
            print(f"[ERROR] Missing dependency file: {dep_path}")
            sys.exit(1)

        with open(dep_path) as f:
            lines = [l.strip() for l in f if l.strip()]

        for line in lines:
            try:
                prio, qual, pkg = line.split()
                prio = int(prio)
            except ValueError:
                print(f"[ERROR] Invalid line in {dep_path}: '{line}'")
                sys.exit(1)

            # Skip dependencies exceeding the DEP_LEVEL
            if prio > self.dep_level:
                print(f" Out: {pkg} (priority {prio} > {self.dep_level})")
                continue

            # Avoid reprocessing already expanded nodes
            if pkg in self.visited:
                print(f" Edge: already processed {pkg}")
                continue

            yaml_path = self._find_yaml_for_package(pkg)
            deps = self._read_yaml_deps(yaml_path)

            pkg_dep_path = os.path.join(self.dep_dir, f"{pkg}.dep")
            with open(pkg_dep_path, "w") as depf:
                for (p, q, name) in deps:
                    depf.write(f"{p} {q} {name}\n")

            self.visited.add(pkg)
            print(f" Node: {pkg} (depth {depth})")

            if not deps:
                print(f" Leaf: {pkg}")
            else:
                # Recurse into dependencies
                self.generate_subgraph(f"{pkg}.dep", prio, depth + 1, qual)

    # -------------------------------------------------------
    def run_pipeline(self, packages: list[str]):
        """
        Run Step 2 + Step 3 as a unified pipeline.
        """
        root_path = self.generate_deps(packages)
        self.generate_subgraph(os.path.basename(root_path), 1, 1, "b")


# -------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Unified dependency resolver (Steps 2+3)")
    parser.add_argument("--packages", required=True, help="Comma-separated list of package names")
    parser.add_argument("--dep-dir", required=True, help="Directory for output .dep files")
    parser.add_argument("--package-dir", required=True, help="Directory containing YAML package files")
    parser.add_argument("--config", required=True, help="TOML configuration with package aliases")
    parser.add_argument("--dep-level", type=int, default=3, help="Maximum dependency weight (1–4)")
    args = parser.parse_args()

    packages = [p.strip() for p in args.packages.split(",") if p.strip()]
    solver = DepSolver(
        dep_dir=args.dep_dir,
        dep_level=args.dep_level,
        package_dir=args.package_dir,
        config_file=args.config
    )

    solver.run_pipeline(packages)


if __name__ == "__main__":
    main()
