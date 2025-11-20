#!/usr/bin/env python3
import argparse
import yaml
from pathlib import Path
from collections import defaultdict, deque
import sys

# Dependency weight mapping
WEIGHTS = {"required": 1, "recommended": 2, "optional": 3, "runtime": 4}


def load_packages(path: Path):
    packages = {}
    for yaml_file in path.glob("*.yaml"):
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f)

        name = data.get("name")
        deps = data.get("dependencies", {})

        normalized = {}
        for cat in ["required", "recommended", "optional", "runtime"]:
            val = deps.get(cat, [])
            if isinstance(val, str):
                val = [v.strip() for v in val.split(",") if v.strip()]
            elif not isinstance(val, list):
                val = []
            normalized[cat] = val
        packages[name] = normalized
    return packages


def build_graph(packages, include):
    max_weight = max(WEIGHTS[d] for d in include if d in WEIGHTS)
    graph = defaultdict(set)

    for pkg, deps in packages.items():
        for cat, deps_list in deps.items():
            if WEIGHTS[cat] <= max_weight:
                for dep in deps_list:
                    graph[pkg].add(dep)
        if pkg not in graph:
            graph[pkg] = set()
    return graph


def get_all_dependencies(root, packages, include):
    max_weight = max(WEIGHTS[d] for d in include if d in WEIGHTS)
    visited = set()
    stack = [root]

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        if current not in packages:
            continue
        for cat, deps in packages[current].items():
            if WEIGHTS[cat] <= max_weight:
                for dep in deps:
                    if dep not in visited:
                        stack.append(dep)
    return visited


def detect_cycles_and_split(graph):
    visited = set()
    stack = []
    rec_stack = set()
    cycles = []

    def dfs(node):
        visited.add(node)
        rec_stack.add(node)
        for dep in graph[node]:
            if dep not in visited:
                dfs(dep)
            elif dep in rec_stack:
                cycles.append((node, dep))
        rec_stack.remove(node)

    for node in graph:
        if node not in visited:
            dfs(node)

    for a, b in cycles:
        # Handle bootstrap cycles by creating synthetic -pass1 node
        pass1_node = f"{a}-pass1"
        if pass1_node not in graph:
            graph[pass1_node] = set()
        if b in graph[a]:
            graph[a].remove(b)
            graph[pass1_node].add(b)
        graph[b].add(a)

    return graph


def topological_sort(graph):
    indegree = {n: 0 for n in graph}
    for n, edges in graph.items():
        for dep in edges:
            indegree[dep] = indegree.get(dep, 0) + 1

    queue = deque([n for n in indegree if indegree[n] == 0])
    order = []

    while queue:
        n = queue.popleft()
        order.append(n)
        for dep in graph.get(n, []):
            indegree[dep] -= 1
            if indegree[dep] == 0:
                queue.append(dep)

    if len(order) != len(indegree):
        raise RuntimeError("Cycle remains in dependency graph after multipass adjustment")

    return order


def print_tree(pkg, packages, include, prefix="", seen=None):
    if seen is None:
        seen = set()
    if pkg in seen:
        print(prefix + f"└── (circular) {pkg}")
        return
    seen.add(pkg)

    max_weight = max(WEIGHTS[d] for d in include if d in WEIGHTS)
    deps = packages.get(pkg, {})
    for cat, items in deps.items():
        if WEIGHTS[cat] <= max_weight and items:
            print(f"{prefix}├── {cat}:")
            for dep in items:
                print(prefix + f"│   ├── {dep}")
                print_tree(dep, packages, include, prefix + "│   ", seen)


def main():
    parser = argparse.ArgumentParser(description="BLFS-style multipass dependency resolver")
    parser.add_argument("--path", required=True, help="Path to directory with YAML package definitions")
    parser.add_argument("--include", type=str, default="required", help="Comma-separated dependency categories")
    parser.add_argument("--roots", nargs="+", required=True, help="Root package(s) or '*' for all")
    parser.add_argument("--tree", action="store_true", help="Display dependency tree")
    parser.add_argument("--output", help="Write build order to file")

    args = parser.parse_args()
    path = Path(args.path)
    include = [x.strip() for x in args.include.replace(",", " ").split() if x.strip()]

    print("[Dependency Resolver]")
    print(f"Included dependency types: {', '.join(include)}")

    packages = load_packages(path)
    all_pkg_names = list(packages.keys())

    if args.roots == ["*"]:
        roots = all_pkg_names
        print("Root packages: ALL")
    else:
        roots = args.roots
        print(f"Root packages: {', '.join(roots)}")

    graph = build_graph(packages, include)

    all_related = set()
    for root in roots:
        all_related |= get_all_dependencies(root, packages, include)
        all_related.add(root)

    subgraph = {n: {d for d in graph[n] if d in all_related} for n in all_related}

    # Apply multipass cycle handling
    subgraph = detect_cycles_and_split(subgraph)

    build_order = topological_sort(subgraph)

    print("\nResolved build order:")
    for i, pkg in enumerate(build_order, 1):
        print(f"{i}. {pkg}")

    if args.output:
        with open(args.output, "w") as f:
            for pkg in build_order:
                f.write(pkg + "\n")
        print(f"\nBuild order written to: {args.output}")

    if args.tree:
        print("\nDependency Tree:")
        for root in roots:
            print(root)
            print_tree(root, packages, include, prefix="  ")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)