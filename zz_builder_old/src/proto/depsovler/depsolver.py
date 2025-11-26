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
        """
        Find YAML file whose name matches the given package.
        Strips name at the last '-' and matches base package.
        Skips packages with blank aliases.
        """
        pkg_alias = self._resolve_package_name(package)

        # --- NEW: skip if alias is blank ---
        if not pkg_alias.strip():
            print(f"[SKIP] Package '{package}' has a blank alias, skipping.")
            return None

        candidates = glob.glob(os.path.join(self.package_dir, "*.yaml"))
        matched_files = []

        for path in candidates:
            base = os.path.basename(path)
            if not base.endswith(".yaml"):
                continue

            name_part = base[:-5]  # strip .yaml
            if "-" not in name_part:
                continue

            pkg_base = name_part.rsplit("-", 1)[0]
            if pkg_base == pkg_alias:
                matched_files.append(path)

        if not matched_files:
            print(f"[ERROR] No YAML file found for package '{package}' (alias: '{pkg_alias}')")
            sys.exit(1)

        # Choose lexicographically latest version if multiple found
        matched_files.sort()
        return matched_files[-1]

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

            # Normalize names to list
            if isinstance(names, str):
                names = [names]
            elif not isinstance(names, list):
                print(f"[WARN] Unexpected type for {key} in {yaml_path}: {type(names).__name__}")
                continue

            # Extract dependency type and qualifier
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

            # Priority and qualifier code
            priority = self.PRIORITY_MAP.get(dep_type, 1)
            qual_map = {
                "before": "b",
                "after": "a",
                "first": "f",
                "external": "b"
            }
            q_code = qual_map.get(qualifier, "b")

            # Special case: optional_external â†’ priority 4, qualifier b
            if key == "optional_external":
                priority = 4
                q_code = "b"

            # --- NEW: skip dependencies beyond dep-level ---
            if priority > self.dep_level:
                continue

            # Write valid dependencies
            for pkg in names:
                pkg = str(pkg).strip()
                if not pkg:
                    continue
                deps.append((priority, q_code, pkg))

        return deps

    # -------------------------------------------------------
    def generate_deps(self, packages: list[str]):
        """
        Step 2 â€” Initialize dependency graph root.
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
        1:1 behavioral match of the original Bash generate_subgraph() function.
        Uses .dep file existence as state (no memory sets).
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

            # Match Bash DEP_LEVEL logic
            if prio > self.dep_level:
                print(f" Out: {pkg} (priority {prio} > {self.dep_level})")
                continue

            pkg_dep_path = os.path.join(self.dep_dir, f"{pkg}.dep")
            if os.path.exists(pkg_dep_path):
                print(f" Edge: {pkg}.dep already exists, skipping")
                continue

            yaml_path = self._find_yaml_for_package(pkg)
            if yaml_path is None:
                # Package intentionally skipped due to blank alias
                continue
                
            deps = self._read_yaml_deps(yaml_path)

            # Write new .dep file
            with open(pkg_dep_path, "w") as depf:
                for (p, q, name) in deps:
                    depf.write(f"{p} {q} {name}\n")

            print(f" Node: {pkg} (depth {depth})")

            if not deps:
                print(f" Leaf: {pkg}")
            else:
                # Recursion occurs immediately (depth-first)
                self.generate_subgraph(f"{pkg}.dep", prio, depth + 1, qual)

    # -------------------------------------------------------
    def clean_subgraph(self):
        """
        Step 4 - Clean and normalize .dep files.
        1. Remove dangling edges
        2. Transform 'after' → 'groupxx' nodes
        3. Transform 'first' → '-pass1' nodes
        """
        dep_files = [
            f for f in glob.glob(os.path.join(self.dep_dir, "*.dep"))
            if os.path.basename(f) != "root.dep"
        ]

        # --- Remove dangling edges ---
        for path in dep_files:
            lines = []
            with open(path) as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) != 3:
                        continue
                    _, _, dep = parts
                    if os.path.exists(os.path.join(self.dep_dir, f"{dep}.dep")):
                        lines.append(line)
            with open(path, "w") as f:
                f.writelines(lines)
        print("[CLEAN] Removed dangling edges")

        # --- Handle 'after' edges ---
        for path in list(dep_files):
            with open(path) as f:
                lines = [l.strip() for l in f if l.strip()]
            after_edges = [l for l in lines if " a " in l]
            if not after_edges:
                continue

            node_base = os.path.basename(path)[:-4]
            group_node = f"{node_base}groupxx"
            group_path = os.path.join(self.dep_dir, f"{group_node}.dep")

            group_lines = [f"1 b {node_base}\n"]
            for l in after_edges:
                prio, _, dep = l.split()
                group_lines.append(f"{prio} b {dep}\n")

            with open(group_path, "w") as f:
                f.writelines(group_lines)
            print(f"[GROUP] Created {group_node}.dep")

            # Replace references in parents
            parent_found = False
            for parent in dep_files + [os.path.join(self.dep_dir, "root.dep")]:
                with open(parent) as f:
                    content = f.read()
                if f" {node_base}\n" in content or content.strip().endswith(f" {node_base}"):
                    new_content = content.replace(f" {node_base}", f" {group_node}")
                    with open(parent, "w") as f:
                        f.write(new_content)
                    parent_found = True
            if not parent_found:
                with open(os.path.join(self.dep_dir, "root.dep"), "a") as f:
                    f.write(f"1 b {group_node}\n")

            # Remove 'a' lines from original
            lines = [l for l in lines if " a " not in l]
            with open(path, "w") as f:
                for l in lines:
                    f.write(l + "\n")
        print("[CLEAN] Processed 'after' edges")

        # --- Handle 'first' edges ---
        for path in list(dep_files):
            with open(path) as f:
                lines = [l.strip() for l in f if l.strip()]
            first_edges = [l for l in lines if " f " in l]
            if not first_edges:
                continue

            node_base = os.path.basename(path)[:-4]
            for l in first_edges:
                prio, _, dep = l.split()
                src_path = os.path.join(self.dep_dir, f"{dep}.dep")
                pass1_path = os.path.join(self.dep_dir, f"{dep}-pass1.dep")

                if os.path.exists(src_path):
                    with open(src_path) as f:
                        dep_lines = [dl for dl in f if dl.strip()]
                    with open(pass1_path, "w") as f:
                        f.writelines(dep_lines)
                    print(f"[PASS1] Created {dep}-pass1.dep")

                # Rewrite in origin
                new_lines = []
                for line in lines:
                    if line == l:
                        new_lines.append(f"1 b {dep}-pass1")
                    else:
                        new_lines.append(line)
                lines = new_lines

                # If orphan, link to root
                linked = any(
                    f" {dep}\n" in open(f).read()
                    for f in dep_files if f != path
                )
                if not linked:
                    with open(os.path.join(self.dep_dir, "root.dep"), "a") as f:
                        f.write(f"1 b {dep}\n")

            with open(path, "w") as f:
                for l in lines:
                    f.write(l + "\n")
        print("[CLEAN] Processed 'first' edges")

    # -------------------------------------------------------
    def run_pipeline(self, packages: list[str]):
        """Run Steps 2–4: generate deps, expand graph, clean it."""
        root_path = self.generate_deps(packages)
        self.generate_subgraph(os.path.basename(root_path), 1, 1, "b")
        self.clean_subgraph()
        print("[PIPELINE] Step 4 complete — graph ready for tree generation.")


# -------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Unified dependency resolver (Steps 2+3)")
    parser.add_argument("--packages", required=True, help="Comma-separated list of package names")
    parser.add_argument("--dep-dir", required=True, help="Directory for output .dep files")
    parser.add_argument("--package-dir", required=True, help="Directory containing YAML package files")
    parser.add_argument("--config", required=True, help="TOML configuration with package aliases")
    parser.add_argument("--dep-level", type=int, default=3, help="Maximum dependency weight (1â€“4)")
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
