#!/usr/bin/env python3
from pathlib import Path
import yaml
import re
import sys
import argparse
import toml
from typing import Optional, Dict

# ───────────────────────────────────────────────
#  GLOBALS
# ───────────────────────────────────────────────
SPACE_STR = " " * 70
DEP_LEVEL = 3
RED, GREEN, YELLOW, MAGENTA, CYAN, OFF = (
    "\033[31m", "\033[32m", "\033[33m", "\033[35m", "\033[36m", "\033[0m"
)


# ───────────────────────────────────────────────
#  CONFIG HANDLING
# ───────────────────────────────────────────────
def load_aliases(config_path: Optional[Path]) -> Dict[str, str]:
    """Load TOML alias mapping from [package_alias] section."""
    if not config_path:
        return {}
    if not config_path.exists():
        print(f"{YELLOW}WARNING:{OFF} Config file not found: {config_path}")
        return {}
    data = toml.load(config_path)
    return data.get("package_alias", {})


def locate_yaml(pkg_name: str, yaml_dir: Path, aliases: dict) -> Path:
    """Find YAML file, honoring alias mapping and version variants."""
    alias_target = aliases.get(pkg_name)
    if alias_target:
        alias_file = yaml_dir / f"{alias_target}.yaml"
        if alias_file.exists():
            print(f"{MAGENTA}Alias:{OFF} {pkg_name} → {alias_target}")
            return alias_file
        print(f"{RED}FATAL:{OFF} Alias '{pkg_name}={alias_target}' not found in {yaml_dir}")
        sys.exit(1)

    # Try exact name and versioned variants
    matches = list(yaml_dir.glob(f"{pkg_name}.yaml")) + list(yaml_dir.glob(f"{pkg_name}-*.yaml"))
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        print(f"{YELLOW}ERROR:{OFF} Multiple YAML files found for '{pkg_name}': {[m.name for m in matches]}")
        print(f"Specify alias in config.toml to disambiguate.")
        sys.exit(1)

    print(f"{RED}FATAL:{OFF} No YAML found for {pkg_name} in {yaml_dir}")
    sys.exit(1)


# ───────────────────────────────────────────────
#  PASS 1: YAML → .DEP GENERATION
# ───────────────────────────────────────────────
def parse_yaml_dependencies(yaml_path: Path) -> list[dict]:
    with yaml_path.open("r") as f:
        data = yaml.safe_load(f)

    deps = []
    dep_tree = data.get("dependencies", {})
    if not dep_tree:
        return deps

    mapping = {"required": 1, "recommended": 2, "optional": 3, "external": 4}
    for level, weight in mapping.items():
        for qualifier in ["first", "before", "after", "external"]:
            key = f"{level}_{qualifier}"
            if key not in dep_tree:
                continue
            names = dep_tree[key].get("name", [])
            if not names:
                continue
            if isinstance(names, str):
                names = [names]
            q = qualifier[0] if qualifier != "external" else "b"
            for n in names:
                deps.append({"weight": weight, "qualifier": q, "target": n})
    return deps


def generate_subgraph(dep_file: Path, weight: int, depth: int, qualifier: str,
                      yaml_dir: Path, dep_level: int, aliases: dict):
    spacing = 1 if depth < 10 else 0
    priostring = {1: "required", 2: "recommended", 3: "optional"}.get(weight, "")
    print(f"\nNode: {depth}{SPACE_STR[:depth+spacing]}{RED}{dep_file.stem}{OFF} {priostring}")

    yaml_path = locate_yaml(dep_file.stem, yaml_dir, aliases)
    dependencies = parse_yaml_dependencies(yaml_path)

    with dep_file.open("w") as f:
        for dep in dependencies:
            f.write(f"{dep['weight']} {dep['qualifier']} {dep['target']}\n")

    for dep in dependencies:
        if dep["weight"] > dep_level:
            print(f" Out: {YELLOW}{dep['target']}{OFF}")
            continue

        dep_path = dep_file.parent / f"{dep['target']}.dep"
        if dep_path.exists():
            print(f" Edge: {MAGENTA}{dep['target']}{OFF}")
            continue

        try:
            sub_yaml = locate_yaml(dep["target"], yaml_dir, aliases)
        except SystemExit:
            print(f"{YELLOW}WARN:{OFF} Missing dependency YAML for {dep['target']}")
            continue

        sub_deps = parse_yaml_dependencies(sub_yaml)
        if not sub_deps:
            dep_path.touch()
            print(f" Leaf: {CYAN}{dep['target']}{OFF}")
        else:
            generate_subgraph(dep_path, dep["weight"], depth + 1, dep["qualifier"], yaml_dir, dep_level, aliases)

    print(f" End: {depth}{GREEN}{dep_file.stem}{OFF}")
    return 0


# ───────────────────────────────────────────────
#  PASS 2: CLEAN & TRANSFORM GRAPH
# ───────────────────────────────────────────────
def path_to(start_file: Path, target: str, max_weight: int, seen: set, dep_dir: Path) -> bool:
    if start_file.stem == target:
        return True
    seen.add(start_file.stem)
    if not start_file.exists() or start_file.stat().st_size == 0:
        return False
    with start_file.open() as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) != 3:
                continue
            weight, _, dep = parts
            if int(weight) > max_weight:
                continue
            if dep in seen:
                continue
            if path_to(dep_dir / f"{dep}.dep", target, max_weight, seen, dep_dir):
                return True
    return False


def clean_subgraph(dep_dir: Path):
    print(f"\n{MAGENTA}Pass 2: Cleaning dependency files...{OFF}")
    dep_files = list(dep_dir.glob("*.dep"))

    # Step 1: Remove dangling edges
    for node in dep_files:
        if node.name == "root.dep":
            continue
        valid_lines = []
        with node.open() as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) != 3:
                    continue
                _, _, dep = parts
                if (dep_dir / f"{dep}.dep").exists():
                    valid_lines.append(line.strip())
        node.write_text("\n".join(valid_lines) + ("\n" if valid_lines else ""))

    # Step 2: Handle "after" edges
    for node in dep_files:
        if node.name == "root.dep":
            continue
        lines = node.read_text().splitlines()
        after_edges = [l for l in lines if " a " in l]
        if not after_edges:
            continue
        group_name = f"{node.stem}groupxx"
        group_file = dep_dir / f"{group_name}.dep"
        print(f"Processing runtime deps in {node.name}")

        parents = [p for p in dep_files if p != node and f" {node.stem}" in p.read_text()]
        b_flag = False
        for parent in parents:
            p_flag = False
            for line in after_edges:
                _, _, dep = line.split()
                if path_to(dep_dir / f"{dep}.dep", parent.stem, 3, set(), dep_dir):
                    p_flag = True
                    break
            if not p_flag:
                b_flag = True
                text = parent.read_text()
                text = re.sub(rf"\s{node.stem}$", f" {group_name}", text, flags=re.MULTILINE)
                parent.write_text(text)

        group_lines = [f"1 b {node.stem}"] + [re.sub(r" a ", " b ", l) for l in after_edges]
        group_file.write_text("\n".join(group_lines) + "\n")

        if not b_flag:
            with (dep_dir / "root.dep").open("a") as root_file:
                root_file.write(f"1 b {group_name}\n")

        filtered = [l for l in lines if " a " not in l]
        node.write_text("\n".join(filtered) + "\n")

    # Step 3: Handle "first" edges
    for node in dep_files:
        lines = node.read_text().splitlines()
        first_edges = [l for l in lines if " f " in l]
        if not first_edges:
            continue
        print(f"Processing 'first' deps in {node.name}")

        for line in first_edges:
            w, _, dep = line.split()
            dep_file = dep_dir / f"{dep}.dep"
            dep_pass1 = dep_dir / f"{dep}-pass1.dep"
            if dep_file.exists():
                dep_pass1.write_text(dep_file.read_text())
            else:
                continue
            pruned = []
            with dep_pass1.open() as f:
                for l2 in f:
                    parts = l2.strip().split()
                    if len(parts) != 3:
                        continue
                    _, _, start = parts
                    if not path_to(dep_dir / f"{start}.dep", node.stem, int(w), set(), dep_dir):
                        pruned.append(l2.strip())
            dep_pass1.write_text("\n".join(pruned) + "\n")
            text = node.read_text()
            text = re.sub(rf"{w} f {dep}$", f"1 b {dep}-pass1", text, flags=re.MULTILINE)
            node.write_text(text)

    print(f"{GREEN}Pass 2 complete.{OFF}")


# ───────────────────────────────────────────────
#  PASS 3: DEPENDENCY TREE CONSTRUCTION
# ───────────────────────────────────────────────
def generate_dependency_tree(dep_file: Path, dep_dir: Path, visited: set, depth: int = 0):
    """Recursively expand .dep into .tree"""
    tree_file = dep_dir / f"{dep_file.stem}.tree"
    indent = " " * (depth * 2)

    if dep_file.stem in visited:
        print(f"{YELLOW}Cycle detected:{OFF} {' -> '.join(list(visited) + [dep_file.stem])}")
        return

    visited.add(dep_file.stem)
    if not dep_file.exists():
        print(f"{YELLOW}WARN:{OFF} Missing {dep_file.name}, skipping...")
        return

    lines = dep_file.read_text().splitlines()
    if not lines:
        return

    tree_lines = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) != 3:
            continue
        weight, qualifier, target = parts
        tree_lines.append(f"{indent}{weight} {qualifier} {target}")

        target_file = dep_dir / f"{target}.dep"
        if not target_file.exists():
            continue
        generate_dependency_tree(target_file, dep_dir, visited.copy(), depth + 1)

    tree_file.write_text("\n".join(tree_lines) + "\n")


# ───────────────────────────────────────────────
#  FULL PIPELINE
# ───────────────────────────────────────────────
def build_dependency_graph(root_pkg: str, yaml_dir: Path, output_dir: Path,
                           dep_level: int, aliases: dict):
    output_dir.mkdir(exist_ok=True)
    root_dep = output_dir / f"{root_pkg}.dep"
    print(f"{CYAN}Building dependency graph for {root_pkg}{OFF}")

    generate_subgraph(root_dep, 1, 1, "b", yaml_dir, dep_level, aliases)
    clean_subgraph(output_dir)
    print(f"{CYAN}Generating dependency tree for {root_pkg}{OFF}")
    generate_dependency_tree(root_dep, output_dir, set())
    print(f"{GREEN}Dependency graph + tree generation complete.{OFF}")


# ───────────────────────────────────────────────
#  CLI
# ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Generate full dependency graph (.dep + .tree) from YAML definitions with TOML aliasing."
    )
    parser.add_argument("root_package", help="Root package (without extension)")
    parser.add_argument("-y", "--yaml-dir", required=True, help="Directory containing YAML package files")
    parser.add_argument("-o", "--output-dir", default="dependencies", help="Directory for generated .dep files")
    parser.add_argument("-l", "--level", type=int, choices=[1, 2, 3, 4], default=DEP_LEVEL,
                        help="Dependency depth level (1=required, 4=external)")
    parser.add_argument("-c", "--config", type=Path, default=Path("depsolver.toml"),
                        help="TOML alias config file path")

    args = parser.parse_args()
    yaml_dir = Path(args.yaml_dir)
    output_dir = Path(args.output_dir)
    aliases = load_aliases(args.config)

    build_dependency_graph(args.root_package, yaml_dir, output_dir, args.level, aliases)


if __name__ == "__main__":
    main()
