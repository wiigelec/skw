#!/usr/bin/env python3
import os, re, sys, yaml, shutil
from pathlib import Path
from typing import Dict, List, Set, Optional

RED, GREEN, YELLOW, MAGENTA, CYAN, OFF = (
    "\033[31m", "\033[32m", "\033[33m", "\033[35m", "\033[36m", "\033[0m"
)
SPACE_STR = " " * 70
DEP_LEVEL = 3

# ───────────────────────────────
# Utility functions
# ───────────────────────────────
def parse_yaml_dependencies(yaml_path: Path) -> List[dict]:
    with yaml_path.open() as f:
        data = yaml.safe_load(f)

    deps, dep_tree = [], data.get("dependencies", {})
    mapping = {"required": 1, "recommended": 2, "optional": 3, "external": 4}

    for level, weight in mapping.items():
        for qualifier in ["before", "after", "first"]:
            key = f"{level}_{qualifier}"
            if key not in dep_tree:
                continue
            names = dep_tree[key]
            if isinstance(names, str):
                names = [names]
            q = qualifier[0]
            for n in names:
                deps.append({"weight": weight, "qualifier": q, "target": n})
    return deps


def path_to(start: Path, target: str, dep_dir: Path, max_weight: int, seen: Optional[Set[str]] = None) -> bool:
    if seen is None:
        seen = set()
    node = start.stem
    if node == target:
        return True
    seen.add(node)
    if not start.exists():
        return False
    for line in start.read_text().splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        w, _, dep = parts
        if int(w) > max_weight or dep in seen:
            continue
        if path_to(dep_dir / f"{dep}.dep", target, dep_dir, max_weight, seen.copy()):
            return True
    return False


def generate_subgraph(dep_file: Path, weight: int, depth: int, qualifier: str, yaml_dir: Path, dep_level: int):
    spacing = 1 if depth < 10 else 0
    priostring = {1: "required", 2: "recommended", 3: "optional"}.get(weight, "")
    print(f"\nNode: {depth}{SPACE_STR[:depth+spacing]}{RED}{dep_file.stem}{OFF} {priostring}")

    yaml_file = yaml_dir / f"{dep_file.stem}.yaml"
    if not yaml_file.exists():
        print(f"{YELLOW}Warning:{OFF} Missing YAML for {dep_file.stem}")
        return

    deps = parse_yaml_dependencies(yaml_file)
    lines = [f"{d['weight']} {d['qualifier']} {d['target']}" for d in deps]
    dep_file.write_text("\n".join(lines) + "\n")

    for d in deps:
        if d["weight"] > dep_level:
            print(f" Out: {depth+1}{SPACE_STR[:depth]}{YELLOW}{d['target']}{OFF} filtered")
            continue
        dep_path = dep_file.parent / f"{d['target']}.dep"
        if dep_path.exists():
            print(f" Seen: {depth+1}{SPACE_STR[:depth]}{CYAN}{d['target']}{OFF}")
            continue
        sub_yaml = yaml_dir / f"{d['target']}.yaml"
        if not sub_yaml.exists():
            dep_path.touch()
            print(f"Leaf: {depth+1}{SPACE_STR[:depth]}{GREEN}{d['target']}{OFF}")
        else:
            generate_subgraph(dep_path, d["weight"], depth + 1, d["qualifier"], yaml_dir, dep_level)
    print(f" End: {depth}{SPACE_STR[:depth]}{GREEN}{dep_file.stem}{OFF}")


def clean_subgraph(dep_dir: Path):
    print(f"{MAGENTA}Cleaning graph...{OFF}")

    for node in dep_dir.glob("*.dep"):
        if node.name == "root.dep":
            continue
        lines = []
        for line in node.read_text().splitlines():
            parts = line.split()
            if len(parts) == 3 and (dep_dir / f"{parts[2]}.dep").exists():
                lines.append(line)
        node.write_text("\n".join(lines) + "\n")

    # after -> groupxx
    for node in dep_dir.glob("*.dep"):
        if ' a ' not in node.read_text():
            continue
        group_name = f"{node.stem}groupxx"
        group_file = dep_dir / f"{group_name}.dep"
        group_lines = [f"1 b {node.stem}"]
        for line in node.read_text().splitlines():
            if ' a ' in line:
                rewritten = re.sub(' a ', ' b ', line)
                group_lines.append(rewritten)
        group_file.write_text("\n".join(group_lines) + "\n")
        filtered = [l for l in node.read_text().splitlines() if ' a ' not in l]
        node.write_text("\n".join(filtered) + "\n")

    # first -> pass1
    for node in dep_dir.glob("*.dep"):
        lines = node.read_text().splitlines()
        if not any(' f ' in l for l in lines):
            continue
        new_lines = []
        for line in lines:
            parts = line.split()
            if len(parts) != 3:
                new_lines.append(line)
                continue
            w, q, t = parts
            if q == 'f':
                src = dep_dir / f"{t}.dep"
                dst = dep_dir / f"{t}-pass1.dep"
                if src.exists():
                    shutil.copy(src, dst)
                filt_lines = []
                for pline in dst.read_text().splitlines():
                    pparts = pline.split()
                    if len(pparts) != 3:
                        filt_lines.append(pline)
                        continue
                    pw, pq, pt = pparts
                    if path_to(dep_dir / f"{pt}.dep", node.stem, dep_dir, int(pw)):
                        continue
                    filt_lines.append(pline)
                dst.write_text("\n".join(filt_lines) + "\n")
                new_lines.append(f"1 b {t}-pass1")
            else:
                new_lines.append(line)
        node.write_text("\n".join(new_lines) + "\n")


def generate_dependency_tree(dep_dir: Path):
    print(f"{CYAN}Generating .tree files...{OFF}")
    for dep_file in dep_dir.glob('*.dep'):
        name = dep_file.stem
        lines = dep_file.read_text().splitlines()
        if not lines:
            continue
        tree_file = dep_dir / f"{name}.tree"
        depth = 1
        with tree_file.open('w') as tf:
            tf.write(f"{name}\n")
            for l in lines:
                w, q, t = l.split()
                tf.write(f"  {'  '*depth}{t} ({q})\n")


def topological_sort(dep_dir: Path):
    print(f"{CYAN}Generating topological order...{OFF}")
    adj: Dict[str, List[str]] = {}
    for f in dep_dir.glob("*.dep"):
        name = f.stem
        deps = []
        for line in f.read_text().splitlines():
            parts = line.split()
            if len(parts) == 3:
                deps.append(parts[2])
        adj[name] = deps

    visited, stack, order = set(), set(), []

    def dfs(n: str):
        if n in visited:
            return
        if n in stack:
            print(f"{YELLOW}Cycle detected at {n}{OFF}")
            return
        stack.add(n)
        for d in adj.get(n, []):
            if d in adj:
                dfs(d)
        stack.remove(n)
        visited.add(n)
        order.append(n)

    for n in adj:
        if n not in visited:
            dfs(n)

    order = [o for o in reversed(order) if not (o.endswith('groupxx') or o.endswith('-pass1') or o == 'root')]
    (dep_dir / 'build_order.txt').write_text("\n".join(order) + "\n")
    print(f"{GREEN}Build order computed with {len(order)} packages{OFF}")


def main():
    yaml_dir = Path(sys.argv[1])
    dep_dir = Path(sys.argv[2])
    dep_dir.mkdir(exist_ok=True)
    root_dep = dep_dir / 'root.dep'
    root_dep.write_text('1 b root\n')

    generate_subgraph(root_dep, 1, 1, 'b', yaml_dir, DEP_LEVEL)
    clean_subgraph(dep_dir)
    generate_dependency_tree(dep_dir)
    topological_sort(dep_dir)

if __name__ == '__main__':
    main()
