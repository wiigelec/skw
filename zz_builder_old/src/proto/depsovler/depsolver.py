import argparse
import yaml
import tomllib
from pathlib import Path

class SKWDepSolver:
    """Dependency graph builder converting YAML package metadata into .dep files, including groupxx support and alias mapping via TOML."""

    def __init__(self, yaml_dir: str, output_dir: str, dep_level: int = 3, config_file: str | None = None):
        self.yaml_dir = Path(yaml_dir)
        self.output_dir = Path(output_dir)
        self.dep_level = int(dep_level)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        if not self.yaml_dir.is_dir():
            raise FileNotFoundError(f"YAML directory {self.yaml_dir} not found")

        # Load config.toml aliases if provided
        self.aliases = {}
        if config_file:
            cfg_path = Path(config_file)
            if cfg_path.exists():
                with open(cfg_path, "rb") as f:
                    cfg = tomllib.load(f)
                    self.aliases = cfg.get("package_aliases", {})
                    print(f"Loaded {len(self.aliases)} alias mappings from {cfg_path}")

    def load_yaml(self, package_name: str) -> dict:
        """Load YAML for a given package name, matching versioned files carefully and applying aliases."""
        if package_name in self.aliases:
            print(f"Alias applied: {package_name} → {self.aliases[package_name]}")
            package_name = self.aliases[package_name]

        matches = list(self.yaml_dir.glob(f"{package_name}-*.yaml"))

        if not matches and any(ch.isdigit() for ch in package_name):
            base = package_name.rstrip("0123456789")
            matches = list(self.yaml_dir.glob(f"{base}-*.yaml"))

        if not matches:
            raise FileNotFoundError(f"No YAML found for package '{package_name}' in {self.yaml_dir}")
        if len(matches) > 1:
            matches.sort(key=lambda p: len(p.stem))
            print(f"⚠️  Multiple YAMLs for '{package_name}', using: {matches[0].name}")

        file_path = matches[0]
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def clean_deps(self):
        for f in self.output_dir.glob("*.dep"):
            f.unlink()
        print(f"Cleaned existing .dep files in {self.output_dir}")

    def generate_dep_file(self, package_name: str, depth: int = 1, visited=None):
        visited = visited or set()
        if package_name in visited:
            return
        visited.add(package_name)

        data = self.load_yaml(package_name)
        deps = data.get("dependencies", {})

        dep_map = {"required": 1, "recommended": 2, "optional": 3}

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
                        if phase != "external":
                            try:
                                self.generate_dep_file(dep, depth + 1, visited)
                            except FileNotFoundError:
                                pass
        print(f"Generated: {out_file}")

    def clean_subgraph(self):
        dep_files = list(self.output_dir.glob("*.dep"))
        for dep_file in dep_files:
            node_name = dep_file.stem
            group_file = self.output_dir / f"{node_name}groupxx.dep"

            if group_file.exists():
                continue

            with open(dep_file, "r", encoding="utf-8") as src:
                lines = src.readlines()

            after_deps = [ln for ln in lines if ' a ' in ln]
            if after_deps:
                print(f"Creating groupxx for {node_name} (after dependencies detected)")
                with open(group_file, "w", encoding="utf-8") as gf:
                    gf.write(f"1 b {node_name}\n")
                    for ln in after_deps:
                        prio, build, dep = ln.strip().split()
                        gf.write(f"{prio} b {dep}\n")
                for parent_file in dep_files:
                    if parent_file == dep_file:
                        continue
                    txt = parent_file.read_text()
                    new_txt = txt.replace(f" {node_name}\n", f" {node_name}groupxx\n")
                    if new_txt != txt:
                        parent_file.write_text(new_txt)
        print("Subgraph cleanup complete. Groupxx files generated.")

    @classmethod
    def cli(cls):
        parser = argparse.ArgumentParser(
            description="Generate .dep dependency files from YAML package metadata with alias + groupxx support."
        )
        parser.add_argument("package", help="Root package name (without .yaml extension).")
        parser.add_argument("--yaml-dir", required=True, help="Directory containing package YAML files.")
        parser.add_argument("--output", required=True, help="Directory where .dep files will be written.")
        parser.add_argument("--dep-level", type=int, default=3, choices=[1, 2, 3], help="Dependency level.")
        parser.add_argument("--config", help="Path to TOML configuration file with alias mappings.")
        parser.add_argument("--clean", action="store_true", help="Clean existing .dep files.")
        parser.add_argument("--clean-subgraph", action="store_true", help="Perform groupxx cleanup after generation.")

        args = parser.parse_args()
        solver = cls(args.yaml_dir, args.output, args.dep_level, args.config)

        if args.clean:
            solver.clean_deps()

        solver.generate_dep_file(args.package)

        if args.clean_subgraph:
            solver.clean_subgraph()

if __name__ == "__main__":
    SKWDepSolver.cli()
