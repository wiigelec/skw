import os
import yaml
import toml
import argparse
from pathlib import Path
from typing import Dict, List, Set


class DepSolver:
    def __init__(self, dep_dir: str, alias_file: str = None):
        self.dep_dir = Path(dep_dir)
        self.aliases = {}
        if alias_file and Path(alias_file).exists():
            cfg = toml.load(alias_file)
            self.aliases = cfg.get("package_aliases", {})

    def _normalize_name(self, filename: str) -> str:
        name = Path(filename).stem
        # remove version suffix (after last '-')
        if '-' in name:
            name = name[:name.rfind('-')]
        # apply alias mapping if any
        return self.aliases.get(name, name)

    def _load_package(self, pkg_name: str) -> Dict:
        for yaml_file in self.dep_dir.glob(f"{pkg_name}-*.yaml"):
            with open(yaml_file, 'r') as f:
                return yaml.safe_load(f)
        # try aliases if not found
        if pkg_name in self.aliases:
            alias = self.aliases[pkg_name]
            for yaml_file in self.dep_dir.glob(f"{alias}-*.yaml"):
                with open(yaml_file, 'r') as f:
                    return yaml.safe_load(f)
        raise FileNotFoundError(f"No dependency YAML found for {pkg_name}")

    def generate_dep_files(self, root_pkg: str, dep_level: int = 3):
        visited: Set[str] = set()
        print(f"Generating .dep files from root: {root_pkg} (level {dep_level})")
        self._generate_subgraph(root_pkg, dep_level, visited)

    def _generate_subgraph(self, pkg_name: str, dep_level: int, visited: Set[str]):
        norm_name = self._normalize_name(pkg_name)
        if norm_name in visited:
            return

        visited.add(norm_name)
        pkg_data = self._load_package(norm_name)
        
        dep_path = self.dep_dir / f"{norm_name}.dep"
        deps = pkg_data.get('dependencies', [])

        lines = []
        for dep in deps:
            weight = dep.get('weight', 1)
            qualifier = dep.get('qualifier', 'b')
            dep_name = dep['name']

            if weight > dep_level:
                continue

            lines.append(f"{weight} {qualifier} {dep_name}")
            self._generate_subgraph(dep_name, dep_level, visited)

        with open(dep_path, 'w') as f:
            f.write('\n'.join(lines))

        print(f"Created {dep_path} with {len(lines)} deps")


def main():
    parser = argparse.ArgumentParser(description="Dependency graph .dep generator (YAML-based)")
    parser.add_argument("dep_dir", help="Directory containing YAML package definitions")
    parser.add_argument("root_pkg", help="Root package to start dependency generation from")
    parser.add_argument("--aliases", help="Optional TOML alias mapping file", default=None)
    parser.add_argument("--level", type=int, help="Max dependency weight level (1-4)", default=3)

    args = parser.parse_args()

    solver = DepSolver(args.dep_dir, args.aliases)
    solver.generate_dep_files(args.root_pkg, args.level)


if __name__ == "__main__":
    main()
