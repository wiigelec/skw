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

            # Special case: optional_external Ã¢â€ â€™ priority 4, qualifier b
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
        Step 2 Ã¢â‚¬â€ Initialize dependency graph root.
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
        1:1 translation of the Bash clean_subgraph() from func_dependencies.sh
        ---------------------------------------------------------------------
        Performs:
          - Loop 1: remove dangling edges
          - Loop 2: handle 'after' edges (create groupxx nodes)
          - Loop 3: handle 'first' edges (create -pass1 nodes)
        """

        import re

        dep_files = sorted(
            f for f in glob.glob(os.path.join(self.dep_dir, "*.dep"))
            if os.path.basename(f) != "root.dep"
        )

        # --- Loop 1: Remove dangling edges ---
        for node in dep_files:
            lines_to_remove = []
            with open(node) as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) != 3:
                        continue
                    _, _, dep = parts
                    if not os.path.exists(os.path.join(self.dep_dir, f"{dep}.dep")):
                        lines_to_remove.append(dep)

            if lines_to_remove:
                content = []
                with open(node) as f:
                    for line in f:
                        if not any(line.strip().endswith(f" {d}") for d in lines_to_remove):
                            content.append(line)
                with open(node, "w") as f:
                    f.writelines(content)

        print("[CLEAN] Removed dangling edges")

        # Helper function for path_to() equivalence
        def path_to(start, seek, prio, seen=None):
            if seen is None:
                seen = set()
            if start == seek:
                return True
            seen.add(start)
            start_path = os.path.join(self.dep_dir, f"{start}.dep")
            if not os.path.exists(start_path):
                return False
            with open(start_path) as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) != 3:
                        continue
                    p, _, dep = parts
                    try:
                        p = int(p)
                    except ValueError:
                        continue
                    if p > prio or dep in seen:
                        continue
                    if path_to(dep, seek, prio, seen):
                        return True
            return False

        # --- Loop 2: Process 'after' edges ---
        for node_path in dep_files:
            node = os.path.basename(node_path)
            if node == "root.dep":
                continue
            with open(node_path) as f:
                lines = [l.strip() for l in f if l.strip()]

            after_edges = [l for l in lines if re.search(r"\sa\s", l)]
            if not after_edges:
                continue

            node_base = node[:-4]
            group_node = f"{node_base}groupxx"
            group_path = os.path.join(self.dep_dir, f"{group_node}.dep")

            b_flag = 0  # nothing depends on groupxx yet

            # find parents that depend on this node
            all_files = sorted(glob.glob(os.path.join(self.dep_dir, "*.dep")))
            for parent_path in all_files:
                parent = os.path.basename(parent_path)
                if parent == "root.dep":
                    continue
                with open(parent_path) as f:
                    parent_content = f.read()

                # only consider direct parents
                if not re.search(rf"\b{re.escape(node_base)}\b", parent_content):
                    continue

                p_flag = 0  # no after dependency depends on parent yet
                for line in after_edges:
                    _, _, dep = line.split()
                    if path_to(dep, parent[:-4], 3):
                        p_flag = 1
                        break

                if p_flag == 0:
                    b_flag = 1
                    new_content = re.sub(
                        rf"\b{re.escape(node_base)}\b", f"{node_base}groupxx", parent_content
                    )
                    with open(parent_path, "w") as f:
                        f.write(new_content)

            # Write the groupxx node itself
            with open(group_path, "w") as f:
                f.write(f"1 b {node_base}\n")
                for line in after_edges:
                    prio, _, dep = line.split()
                    f.write(f"{prio} b {dep}\n")

            if b_flag == 0:
                with open(os.path.join(self.dep_dir, "root.dep"), "a") as f:
                    f.write(f"1 b {group_node}\n")

            # Remove 'after' edges from original node
            new_lines = [l for l in lines if not re.search(r"\sa\s", l)]
            with open(node_path, "w") as f:
                f.write("\n".join(new_lines) + "\n")

            print(f"[GROUP] Created {group_node}.dep")

        print("[CLEAN] Processed 'after' edges")

        # --- Loop 3: Process 'first' edges ---
        for node_path in dep_files:
            node = os.path.basename(node_path)
            with open(node_path) as f:
                lines = [l.strip() for l in f if l.strip()]

            first_edges = [l for l in lines if re.search(r"\sf\s", l)]
            if not first_edges:
                continue

            node_base = node[:-4]
            lines_to_change = []

            for line in first_edges:
                _, _, dep = line.split()
                src = os.path.join(self.dep_dir, f"{dep}.dep")
                pass1 = os.path.join(self.dep_dir, f"{dep}-pass1.dep")

                # Copy original dep file
                if os.path.exists(src):
                    with open(src) as f:
                        dep_lines = f.readlines()
                    with open(pass1, "w") as f:
                        f.writelines(dep_lines)
                    print(f"[PASS1] Created {dep}-pass1.dep")

                # remove any circular chain deps
                lr = []
                if os.path.exists(pass1):
                    with open(pass1) as f:
                        for p_line in f:
                            parts = p_line.strip().split()
                            if len(parts) != 3:
                                continue
                            p, _, start = parts
                            if path_to(start, node_base, int(p)):
                                lr.append(start)
                    if lr:
                        with open(pass1) as f:
                            dep_lines = [
                                d for d in f if not any(d.strip().endswith(f" {x}") for x in lr)
                            ]
                        with open(pass1, "w") as f:
                            f.writelines(dep_lines)

                lines_to_change.append(dep)

            # rewrite references in node file
            for dep in lines_to_change:
                lines = [
                    re.sub(rf"[0-9]+\sf\s{dep}$", f"1 b {dep}-pass1", l) for l in lines
                ]
                # check if orphan
                linked = False
                for other in dep_files:
                    if other == node_path:
                        continue
                    if dep in open(other).read():
                        linked = True
                        break
                if not linked:
                    with open(os.path.join(self.dep_dir, "root.dep"), "a") as f:
                        f.write(f"1 b {dep}\n")

            with open(node_path, "w") as f:
                f.write("\n".join(lines) + "\n")

        print("[CLEAN] Processed 'first' edges")



    # -------------------------------------------------------
    def run_pipeline(self, packages: list[str]):
        """Run Steps 2â€“4: generate deps, expand graph, clean it."""
        root_path = self.generate_deps(packages)
        self.generate_subgraph(os.path.basename(root_path), 1, 1, "b")
        self.clean_subgraph()
        print("[PIPELINE] Step 4 complete â€” graph ready for tree generation.")


# -------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Unified dependency resolver (Steps 2+3)")
    parser.add_argument("--packages", required=True, help="Comma-separated list of package names")
    parser.add_argument("--dep-dir", required=True, help="Directory for output .dep files")
    parser.add_argument("--package-dir", required=True, help="Directory containing YAML package files")
    parser.add_argument("--config", required=True, help="TOML configuration with package aliases")
    parser.add_argument("--dep-level", type=int, default=3, help="Maximum dependency weight (1Ã¢â‚¬â€œ4)")
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
