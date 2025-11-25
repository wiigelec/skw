import argparse
import yaml
from pathlib import Path


class SKWDepSolver:
    """Dependency graph builder converting YAML package metadata into .dep files."""

    def __init__(self, yaml_dir: str, output_dir: str, dep_level: int = 3):
        self.yaml_dir = Path(yaml_dir)
        self.output_dir = Path(output_dir)
        self.dep_level = int(dep_level)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        if not self.yaml_dir.is_dir():
            raise FileNotFoundError(f"YAML directory {self.yaml_dir} not found")

    def load_yaml(self, package_name: str) -> dict:
        """Load YAML for a given package name, matching versioned or close variants."""
        # Exact match first (e.g. glib2-*.yaml)
        matches = list(self.yaml_dir.glob(f"{package_name}-*.yaml"))
        
        # If not found, try a relaxed match (ignore digits and dashes)
        if not matches:
            simplified = "".join(filter(str.isalpha, package_name))
            relaxed = [p for p in self.yaml_dir.glob("*.yaml")
                    if simplified.lower() in p.stem.replace("-", "").lower()]
            matches = relaxed

        if not matches:
            raise FileNotFoundError(f"No YAML found for package '{package_name}' in {self.yaml_dir}")

        if len(matches) > 1:
            print(f"Warning: multiple YAML files for {package_name}, using {matches[0].name}")

        file_path = matches[0]
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def clean_deps(self):
        """Remove all .dep files from output directory."""
        for f in self.output_dir.glob("*.dep"):
            f.unlink()
        print(f"Cleaned existing .dep files in {self.output_dir}")

    def generate_dep_file(self, package_name: str, depth: int = 1, visited=None):
        """Generate .dep file recursively for a given package."""
        visited = visited or set()
        if package_name in visited:
            return  # Prevent circular recursion
        visited.add(package_name)

        data = self.load_yaml(package_name)
        deps = data.get("dependencies", {})

        dep_map = {
            "required": 1,
            "recommended": 2,
            "optional": 3,
        }

        out_file = self.output_dir / f"{package_name}.dep"
        with open(out_file, "w", encoding="utf-8") as f:
            for level_name, level_code in dep_map.items():
                if level_code > self.dep_level:
                    continue
                for phase in ("first", "before", "after", "external"):
                    key = f"{level_name}_{phase}"
                    if key not in deps or not deps[key]:
                        continue
                    names = deps[key].get("name")
                    if not names:
                        continue
                    if isinstance(names, str):
                        names = [names]
                    build_char = {
                        "first": "f",
                        "before": "b",
                        "after": "a",
                        "external": "l",
                    }.get(phase, "a")

                    for dep in names:
                        dep = dep.strip()
                        if not dep:
                            continue
                        f.write(f"{level_code} {build_char} {dep}\n")
                        # Recurse only for non-external deps
                        if phase != "external":
                            try:
                                self.generate_dep_file(dep, depth + 1, visited)
                            except FileNotFoundError:
                                pass  # Skip missing YAMLs

        print(f"Generated: {out_file}")

    @classmethod
    def cli(cls):
        parser = argparse.ArgumentParser(
            description="Generate .dep dependency files from YAML package metadata."
        )
        parser.add_argument(
            "package",
            help="Root package name (without .yaml extension) to generate deps for."
        )
        parser.add_argument(
            "--yaml-dir", required=True,
            help="Directory containing package YAML files."
        )
        parser.add_argument(
            "--output", required=True,
            help="Directory where .dep files will be written."
        )
        parser.add_argument(
            "--dep-level", type=int, default=3, choices=[1, 2, 3],
            help="Dependency level: 1=required, 2=required+recommended, 3=all."
        )
        parser.add_argument(
            "--clean", action="store_true",
            help="Clean existing .dep files before generating new ones."
        )

        args = parser.parse_args()
        solver = cls(args.yaml_dir, args.output, args.dep_level)

        if args.clean:
            solver.clean_deps()

        solver.generate_dep_file(args.package)


if __name__ == "__main__":
    SKWDepSolver.cli()
