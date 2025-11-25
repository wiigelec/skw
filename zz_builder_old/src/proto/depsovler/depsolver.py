#!/usr/bin/env python3
from pathlib import Path
import yaml, toml, json, re, sys, argparse
from typing import Dict, List, Set, Optional

# ───────────────────────────────
# Terminal colors
# ───────────────────────────────
RED, GREEN, YELLOW, MAGENTA, CYAN, OFF = (
    "\033[31m", "\033[32m", "\033[33m", "\033[35m", "\033[36m", "\033[0m"
)
SPACE_STR = " " * 70
DEP_LEVEL = 3


# ───────────────────────────────
# Config loader
# ───────────────────────────────
def load_aliases(config_path: Optional[Path]) -> Dict[str, str]:
    """Load aliases from TOML config."""
    if not config_path or not config_path.exists():
        return {}
    data = toml.load(config_path)
    return data.get("package_alias", {})


# ───────────────────────────────
# Locate YAML
# ───────────────────────────────
def locate_yaml(pkg_name: str, yaml_dir: Path, aliases: dict) -> Path:
    alias_target = aliases.get(pkg_name)
    if alias_target:
        alias_file = yaml_dir / f"{alias_target}.yaml"
        if alias_file.exists():
            print(f"{MAGENTA}Alias:{OFF} {pkg_name} → {alias_target}")
            return alias_file
        print(f"{RED}FATAL:{OFF} Alias '{pkg_name}={alias_target}' not found in {yaml_dir}")
        sys.exit(1)

    matches = list(yaml_dir.glob(f"{pkg_name}.yaml")) + list(yaml_dir.glob(f"{pkg_name}-*.yaml"))
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        print(f"{YELLOW}ERROR:{OFF} Multiple YAML files found for '{pkg_name}': {[m.name for m in matches]}")
        sys.exit(1)

    print(f"{RED}FATAL:{OFF} No YAML found for {pkg_name} in {yaml_dir}")
    sys.exit(1)


# ───────────────────────────────
# PASS 1 — YAML → .dep
# ───────────────────────────────
def parse_yaml_dependencies(yaml_path: Path) -> List[dict]:
    with yaml_path.open() as f:
        data = yaml.safe_load(f)

    deps, dep_tree = [], data.get("dependencies", {})
    mapping = {"required": 1, "recommended": 2, "optional": 3, "external": 4}

    for level, weight in mapping.items():
        for qualifier in ["first", "before", "after", "external"]:
            key = f"{level}_{qualifier}"
            if key not in dep_tree:
                continue
            names = dep_tree[key].get("name", [])
            if isinstance(names, str):
                names = [names]
            q = qualifier[0] if qualifier != "external" else "b"
            for n in names:
                if not n or str(n).strip() == "":
                    continue
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
            continue
        dep_path = dep_file.parent / f"{dep['target']}.dep"
        if dep_path.exists():
            continue

        sub_yaml = locate_yaml(dep["target"], yaml_dir, aliases)
        sub_deps = parse_yaml_dependencies(sub_yaml)
        if not sub_deps:
            dep_path.touch()
        else:
            generate_subgraph(dep_path, dep["weight"], depth + 1, dep["qualifier"], yaml_dir, dep_level, aliases)
    return 0


# ───────────────────────────────
# PASS 2 — Clean / Transform Graph
# ───────────────────────────────
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
        lines = []
        with node.open() as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) != 3:
                    continue
                _, _, dep = parts
                if (dep_dir / f"{dep}.dep").exists():
                    lines.append(line.strip())
        node.write_text("\n".join(lines) + ("\n" if lines else ""))

    # Step 2: Handle "after" edges
    for node in dep_files:
        lines = node.read_text().splitlines()
        after_edges = [l for l in lines if " a " in l]
        if not after_edges:
            continue
        group_name = f"{node.stem}groupxx"
        group_file = dep_dir / f"{group_name}.dep"
        print(f"Processing runtime deps in {node.name}")

        group_lines = [f"1 b {node.stem}"] + [re.sub(r" a ", " b ", l) for l in after_edges]
        group_file.write_text("\n".join(group_lines) + "\n")

        # ⬇ Rewrite parents to reference groupxx (critical Bash behavior)
        for parent in dep_files:
            text = parent.read_text()
            for line in after_edges:
                _, _, dep = line.split()
                pattern = rf"\b{dep}\b"
                text = re.sub(pattern, group_name, text)
            parent.write_text(text)

        # Filter 'after' edges from node
        filtered = [l for l in lines if " a " not in l]
        node.write_text("\n".join(filtered) + "\n")

    print(f"{GREEN}Pass 2 complete.{OFF}")


# ───────────────────────────────
# Build Group Mapping
# ───────────────────────────────
def build_group_mapping(dep_dir: Path) -> dict[str, str]:
    mapping = {}
    referenced_groups = set()

    for dep_file in dep_dir.glob("*.dep"):
        text = dep_file.read_text()
        for match in re.findall(r"([A-Za-z0-9._+-]+groupxx)", text):
            referenced_groups.add(match)

    for group_file in dep_dir.glob("*groupxx.dep"):
        group_name = group_file.stem
        if group_name not in referenced_groups:
            continue
        with group_file.open() as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 3:
                    _, _, target = parts
                    mapping[target] = group_name

    json_path = dep_dir / "group_mapping.json"
    with json_path.open("w") as jf:
        json.dump(mapping, jf, indent=2)
    print(f"{GREEN}Saved refined group mapping → {json_path}{OFF}")

    return mapping


# ───────────────────────────────
# PASS 3 — Generate .tree files
# ───────────────────────────────
def generate_dependency_tree(
    dep_file: Path, dep_dir: Path, group_map: dict[str, str],
    depth: int = 1, parent_weight: int = 1, visited: Set[str] = None, max_depth: int = 100
):
    if visited is None:
        visited = set()
    tree_file = dep_dir / f"{dep_file.stem}.tree"
    node_name = dep_file.stem
    if node_name in visited or depth > max_depth:
        return
    visited.add(node_name)
    if not dep_file.exists():
        return

    header_1 = f"1 {depth} {depth}"
    header_2 = f"1 {parent_weight} {parent_weight}"
    lines, seen = [header_1, header_2], set()

    with dep_file.open() as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) != 3:
                continue
            weight, qualifier, target = parts
            target = group_map.get(target, target)
            if target in seen:
                continue
            seen.add(target)
            lines.append(f"{weight} {qualifier} {target}")

    tree_file.write_text("\n".join(lines) + "\n")

    for line in lines[2:]:
        parts = line.split()
        if len(parts) != 3:
            continue
        weight, _, target = parts
        dep_target = dep_dir / f"{target}.dep"
        if dep_target.exists():
            generate_dependency_tree(dep_target, dep_dir, group_map, depth + 1, int(weight), visited.copy(), max_depth)


def generate_all_trees(dep_dir: Path):
    group_map = build_group_mapping(dep_dir)
    for dep_file in sorted(dep_dir.glob("*.dep")):
        generate_dependency_tree(dep_file, dep_dir, group_map, 1, 1)


def generate_root_tree(dep_dir: Path):
    all_nodes = {f.stem for f in dep_dir.glob("*.dep")}
    referenced = set()
    for dep_file in dep_dir.glob("*.dep"):
        for line in dep_file.read_text().splitlines():
            parts = line.split()
            if len(parts) == 3:
                _, _, target = parts
                referenced.add(target)
    top_level = sorted(all_nodes - referenced)
    root_tree = dep_dir / "root.tree"
    lines = ["1 1 1", "1 1 1"]
    for node in top_level:
        if node.endswith("groupxx") or node.endswith("-pass1"):
            continue
        lines.append(f"1 b {node}")
    root_tree.write_text("\n".join(lines) + "\n")
    print(f"{GREEN}root.tree generated with {len(top_level)} top-level nodes.{OFF}")


# ───────────────────────────────
# PASS 4 — Build Order
# ───────────────────────────────
def generate_build_order(dep_dir: Path):
    deps = {}
    for dep_file in dep_dir.glob("*.dep"):
        name = dep_file.stem
        edges = []
        with dep_file.open() as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 3:
                    _, _, target = parts
                    edges.append(target)
        deps[name] = edges

    visited, order = set(), []

    def visit(node: str, stack: Set[str]):
        if node in visited or node not in deps:
            return
        if node in stack:
            print(f"{YELLOW}Cycle detected:{OFF} {' -> '.join(stack)} -> {node}")
            return
        stack.add(node)
        for dep in deps.get(node, []):
            if dep in deps:
                visit(dep, stack)
        stack.remove(node)
        visited.add(node)
        order.append(node)

    for node in deps:
        visit(node, set())

    build_order = dep_dir / "build_order.txt"
    build_order.write_text("\n".join(order[::-1]) + "\n")
    print(f"{GREEN}build_order.txt generated with {len(order)} entries.{OFF}")


# ───────────────────────────────
# Pipeline
# ───────────────────────────────
def build_dependency_graph(root_pkg: str, yaml_dir: Path, output_dir: Path,
                           dep_level: int, aliases: dict):
    output_dir.mkdir(exist_ok=True)
    root_dep = output_dir / f"{root_pkg}.dep"

    print(f"{CYAN}PASS 1: Generating dependency graph...{OFF}")
    generate_subgraph(root_dep, 1, 1, "b", yaml_dir, dep_level, aliases)

    print(f"{CYAN}PASS 2: Cleaning and transforming graph...{OFF}")
    clean_subgraph(output_dir)

    print(f"{CYAN}PASS 3: Generating .tree files...{OFF}")
    generate_all_trees(output_dir)
    generate_root_tree(output_dir)

    print(f"{CYAN}PASS 4: Computing build order...{OFF}")
    generate_build_order(output_dir)

    print(f"{GREEN}All passes complete successfully!{OFF}")


# ───────────────────────────────
# CLI
# ───────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Full BLFS dependency resolver: YAML → DEP → TREE → BUILD ORDER"
    )
    parser.add_argument("root_package", help="Root package name (no extension)")
    parser.add_argument("-y", "--yaml-dir", required=True, help="YAML metadata directory")
    parser.add_argument("-o", "--output-dir", default="dependencies", help="Output directory")
    parser.add_argument("-l", "--level", type=int, default=DEP_LEVEL, help="Dependency level (1–4)")
    parser.add_argument("-c", "--config", type=Path, default=Path("depsolver.toml"), help="Alias config (TOML)")
    args = parser.parse_args()

    yaml_dir = Path(args.yaml_dir)
    output_dir = Path(args.output_dir)
    aliases = load_aliases(args.config)

    build_dependency_graph(args.root_package, yaml_dir, output_dir, args.level, aliases)


if __name__ == "__main__":
    main()