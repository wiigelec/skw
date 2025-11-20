#!/usr/bin/env python3
import argparse
import yaml
from pathlib import Path
from collections import defaultdict, deque
import sys


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
    graph = defaultdict(set)
    for pkg, deps in packages.items():
        for cat in include:
            for dep in deps.get(cat, []):
                if dep:
                    graph[pkg].add(dep)
        if pkg not in graph:
            graph[pkg] = set()
    return graph


def get_all_dependencies(root, packages, include):
    visited = set()
    stack = [root]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        if current not in packages:
            continue
        for cat in include:
            for dep in packages[current].get(cat, []):
                if dep not in visited:
                    stack.append(dep)
    return visited


def detect_cycle(graph):
    visited = set()
    rec_stack = set()

    def dfs(node, path):
        visited.add(node)
        rec_stack.add(node)
        for dep in graph[node]:
            if dep not in visited:
                if dfs(dep, path + [dep]):
                    return True
            elif dep in rec_stack:
                print("\n[Cycle Detected]: " + " -> ".join(path + [dep]))
                return True
        rec_stack.remove(node)
        return False

    for node in graph:
        if node not in visited:
            if dfs(node, [node]):
                return True
    return False


def topological_sort(graph):
    indegree = {n: 0 for n in graph}
    for n, edges in graph.items():
        for dep in edges:
            indegree[dep] += 1
    q = deque([n for n in graph if indegree[n] == 0])
    order = []
    while q:
        n = q.popleft()
        order.append(n)
        for dep in graph[n]:
            indegree[dep] -= 1
            if indegree[dep] == 0:
                q.append(dep)
    if len(order) != len(graph):
        if detect_cycle(graph):
            raise RuntimeError("Cycle detected in dependencies")
        else:
            raise RuntimeError("Unresolved graph state")
    return order


def print_tree(pkg, packages, include, prefix="", seen=None, global_seen=None):
    if seen is None:
        seen = set()
    if global_seen is None:
        global_seen = set()

    if pkg in seen or pkg in global_seen:
        print(prefix + f"└── (circular) {pkg}")
        return

    seen.add(pkg)
    global_seen.add(pkg)
    deps = packages.get(pkg, {})
    for cat in include:
        items = deps.get(cat, [])
        if items:
            print(f"{prefix}├── {cat}:")
            for dep in items:
                print(prefix + f"│   ├── {dep}")
                print_tree(dep, packages, include, prefix + "│   ", seen, global_seen)


def main():
    parser = argparse.ArgumentParser(description="YAML-based package dependency resolver")
    parser.add_argument("--path", required=True, help="Path to directory with package YAML files")
    parser.add_argument(
        "--include",
        type=str,
        default="required",
        help="Comma-separated dependency categories to include (e.g. required,recommended,optional,runtime)",
    )
    parser.add_argument("--roots", nargs="+", required=True, help="Root package(s) or '*' for all")
    parser.add_argument("--tree", action="store_true", help="Display dependency tree")
    parser.add_argument("--output", help="Write ordered build list to file")

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

    try:
        build_order = topological_sort(subgraph)
        print("\nResolved build order:")
        for i, pkg in enumerate(build_order, 1):
            label = pkg
            if pkg not in packages:
                label += " (missing)"
            print(f"{i}. {label}")
    except RuntimeError as e:
        print(f"\nError: {e}")
        print("\nDependency Tree (for debugging):")
        for root in roots:
            print(root)
            print_tree(root, packages, include, prefix="  ")
        sys.exit(1)

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