import yaml
import toml
from pathlib import Path
from typing import Optional, Set

class SKWDepSolver:
    """Phase 3 Revised: Integrate root.dep generation directly inside clean_subgraph() to match BLFS Bash behavior."""

    def __init__(self, yaml_dir: str, output_dir: str, dep_level: int = 3, config_file: Optional[str] = None):
        self.yaml_dir = Path(yaml_dir)
        self.output_dir = Path(output_dir)
        self.dep_level = int(dep_level)
        self.aliases = {}

        if config_file:
            cfg_path = Path(config_file)
            if cfg_path.exists():
                cfg = toml.load(cfg_path)
                self.aliases = cfg.get("package_aliases", {})
                print(f"Loaded {len(self.aliases)} alias mappings from {cfg_path}")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        if not self.yaml_dir.is_dir():
            raise FileNotFoundError(f"YAML directory {self.yaml_dir} not found.")

    def load_yaml(self, package_name: str) -> dict:
        if package_name in self.aliases:
            print(f"Alias applied: {package_name} → {self.aliases[package_name]}")
            package_name = self.aliases[package_name]

        matches = list(self.yaml_dir.glob(f"{package_name}-*.yaml"))
        if not matches and any(ch.isdigit() for ch in package_name):
            base = package_name.rstrip("0123456789")
            matches = list(self.yaml_dir.glob(f"{base}-*.yaml"))

        if not matches:
            raise FileNotFoundError(f"YAML file for '{package_name}' not found in {self.yaml_dir}")

        if len(matches) > 1:
            matches.sort(key=lambda p: len(p.stem))
            print(f"⚠️  Multiple YAMLs for '{package_name}', using {matches[0].name}")

        with open(matches[0], "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def generate_subgraph(self, pkg_name: str, weight: int = 1, depth: int = 1, qualifier: str = "b"):
        dep_file = self.output_dir / f"{pkg_name}.dep"

        if dep_file.exists():
            return

        print(f"Generating subgraph for {pkg_name} (weight={weight}, depth={depth}, qualifier={qualifier})")
        try:
            data = self.load_yaml(pkg_name)
        except FileNotFoundError as e:
            print(f"❌ {e}")
            return

        deps = data.get("dependencies", {})
        dep_map = {"required": 1, "recommended": 2, "optional": 3}

        with open(dep_file, "w", encoding="utf-8") as f:
            for level_name, level_code in dep_map.items():
                if level_code > self.dep_level:
                    continue

                for phase in ("first", "before", "after", "external"):
                    key = f"{level_name}_{phase}"
                    if key not in deps:
                        continue

                    names = deps[key].get("name")
                    if not names:
                        continue

                    if isinstance(names, str):
                        names = [names]

                    for dep in names:
                        dep = dep.strip()
                        if not dep:
                            continue

                        build_char = {
                            "first": "f",
                            "before": "b",
                            "after": "a",
                            "external": "l",
                        }.get(phase, "b")

                        f.write(f"{level_code} {build_char} {dep}\n")

        with open(dep_file, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) != 3:
                    continue
                prio, qual, dep = parts
                prio = int(prio)
                if prio > self.dep_level:
                    continue
                self.generate_subgraph(dep, prio, depth + 1, qual)

        print(f"Generated: {dep_file}")

    def path_exists(self, start: str, target: str, visited: Optional[Set[str]] = None) -> bool:
        if visited is None:
            visited = set()
        if start in visited:
            return False
        visited.add(start)

        dep_file = self.output_dir / f"{start}.dep"
        if not dep_file.exists():
            return False

        with open(dep_file, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 3:
                    _, _, dep = parts
                    if dep == target:
                        return True
                    if self.path_exists(dep, target, visited):
                        return True
        return False

    def clean_subgraph(self):
        """Replicates BLFS clean_subgraph and generates root.dep inline when orphan groupxx nodes are found."""
        dep_files = list(self.output_dir.glob("*.dep"))
        root_file = self.output_dir / "root.dep"
        if root_file.exists():
            root_file.unlink()

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

        # Identify orphan groupxx nodes (no parents)
        dep_files = list(self.output_dir.glob("*.dep"))
        all_deps = set()
        group_nodes = set()

        for dep_file in dep_files:
            with open(dep_file, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 3:
                        _, _, dep = parts
                        all_deps.add(dep)

        for dep_file in dep_files:
            if dep_file.name.endswith("groupxx.dep"):
                group_nodes.add(dep_file.stem)

        root_nodes = sorted(group_nodes - all_deps)
        if not root_nodes:
            print("⚠️ No root nodes detected.")
        else:
            with open(root_file, "w", encoding="utf-8") as rf:
                for pkg in root_nodes:
                    rf.write(f"1 b {pkg}\n")
            print(f"Generated root.dep with {len(root_nodes)} entries: {', '.join(root_nodes)}")

        print("Subgraph cleaned: groupxx files generated, root.dep created, parent references updated.")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate subgraph, clean it, and produce root.dep (Bash-equivalent).")
    parser.add_argument("package", help="Root package name (without .yaml extension).")
    parser.add_argument("--yaml-dir", required=True, help="Directory containing YAML package metadata.")
    parser.add_argument("--output", required=True, help="Directory for output .dep files.")
    parser.add_argument("--dep-level", type=int, default=3, choices=[1, 2, 3], help="Dependency depth level.")
    parser.add_argument("--config", help="Path to TOML alias config file.")

    args = parser.parse_args()
    solver = SKWDepSolver(args.yaml_dir, args.output, args.dep_level, args.config)
    solver.generate_subgraph(args.package)
    solver.clean_subgraph()