import os
import yaml
import toml
import argparse
from pathlib import Path
from typing import Dict, List, Set


class DepSolver:
    CATEGORY_MAP = {
        'required_first': (1, 'f'),
        'required_before': (1, 'b'),
        'required_after': (1, 'a'),
        'recommended_first': (2, 'f'),
        'recommended_before': (2, 'b'),
        'recommended_after': (2, 'a'),
        'optional_first': (3, 'f'),
        'optional_before': (3, 'b'),
        'optional_after': (3, 'a'),
        'optional_external': (4, 'b'),
    }

    def __init__(self, yaml_dir: str, output_dir: str, alias_file: str = None):
        self.yaml_dir = Path(yaml_dir).expanduser()
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.aliases = {}
        if alias_file and Path(alias_file).exists():
            cfg = toml.load(alias_file)
            self.aliases = cfg.get("package_aliases", {})

    def _normalize_name(self, filename: str) -> str:
        name = Path(filename).stem
        if '-' in name:
            name = name[:name.rfind('-')]
        return self.aliases.get(name, name)

    def _load_package(self, pkg_name: str) -> Dict:
        for yaml_file in self.yaml_dir.glob(f"{pkg_name}-*.yaml"):
            with open(yaml_file, 'r') as f:
                return yaml.safe_load(f)
        if pkg_name in self.aliases:
            alias = self.aliases[pkg_name]
            for yaml_file in self.yaml_dir.glob(f"{alias}-*.yaml"):
                with open(yaml_file, 'r') as f:
                    return yaml.safe_load(f)
        raise FileNotFoundError(f"No YAML found for package: {pkg_name}")

    def generate_subgraph(self, dep_file: str, weight: int, depth: int, qualifier: str, dep_level: int, visited: Set[str]):
        norm_name = self._normalize_name(Path(dep_file).stem)
        if norm_name in visited:
            return

        visited.add(norm_name)
        pkg_data = self._load_package(norm_name)
        
        # Adjust dependency level similar to original bash logic
        if dep_level == 3 and depth > 2:
            dep_level = 2
        elif dep_level > 3:
            dep_level = 3

        deps = self._extract_dependencies(pkg_data, dep_level)
        dep_path = self.output_dir / f"{norm_name}.dep"

        lines = []
        for dep_weight, dep_qual, dep_name in deps:
            if dep_weight > dep_level:
                continue
            lines.append(f"{dep_weight} {dep_qual} {dep_name}")

            # Recurse if dependency not yet seen
            self.generate_subgraph(f"{dep_name}.dep", dep_weight, depth + 1, dep_qual, dep_level, visited)

        with open(dep_path, 'w') as f:
            f.write('\n'.join(lines))

        print(f"Created {dep_path} with {len(lines)} dependencies (depth={depth})")

    def _extract_dependencies(self, pkg_data: Dict, dep_level: int) -> List[tuple]:
        deps = []
        deps_section = pkg_data.get('dependencies', {})
        if not isinstance(deps_section, dict):
            return deps

        for category, (weight, qualifier) in self.CATEGORY_MAP.items():
            if weight > dep_level:
                continue

            entry = deps_section.get(category, {})
            if not entry:
                continue

            names = entry.get('name')
            if not names:
                continue

            if isinstance(names, str):
                deps.append((weight, qualifier, names))
            elif isinstance(names, list):
                for n in names:
                    deps.append((weight, qualifier, n))
        return deps

    def pass1_generate(self, root_pkg: str, dep_level: int = 3):
        visited: Set[str] = set()
        root_path = self.output_dir / "root.dep"
        with open(root_path, 'w') as f:
            f.write(f"1 b {root_pkg}\n")
        print(f"Starting Pass 1: Generating subgraph from root '{root_pkg}' (level={dep_level})")
        self.generate_subgraph(f"{root_pkg}.dep", 1, 1, 'b', dep_level, visited)


def main():
    parser = argparse.ArgumentParser(description="Pass 1: Dependency subgraph generator (YAML-based)")
    parser.add_argument('-y', '--yaml-path', required=True, help='Path to YAML package files')
    parser.add_argument('-o', '--output', required=True, help='Output directory for .dep files')
    parser.add_argument('-l', '--level', type=int, default=3, help='Max dependency weight level (1-4)')
    parser.add_argument('-c', '--config', help='TOML alias configuration file', default=None)
    parser.add_argument('root_pkg', help='Root package name to process')

    args = parser.parse_args()

    solver = DepSolver(args.yaml_path, args.output, args.config)
    solver.pass1_generate(args.root_pkg, args.level)


if __name__ == '__main__':
    main()
