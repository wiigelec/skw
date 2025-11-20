#!/usr/bin/env python3
import argparse
import yaml
from pathlib import Path
from collections import defaultdict, deque
import sys


def load_packages(path: Path):
    """Load all YAML package definitions from the given directory."""
    packages = {}
    for yaml_file in path.glob("*.yaml"):
        with open(yaml_file, "r") as f:
            data = yaml.safe_load(f)

        name = data.get("name")
        deps = data.get("dependencies", {})

        # Normalize dependency fields (ensure lists)
        normalized = {}
        for cat in ["required", "recommended", "optional", "runtime"]:
            val = deps.get(cat, [])
            if isinstance(val, str) and val.strip():
                normalized[cat] = [v.strip() for v in val.split(",")]
            elif isinstance(val, list):
                normalized[cat] = val
            else:
                normalized[cat] = []

        packages[name] = normalized
    return packages


def build_graph(packages, include):
    """Build a dependency graph based on selected categories."""
    graph = defaultdict(set)
    for pkg, deps in packages.items():
        for cat in include:
            for dep in deps.get(cat, []):
                if dep:
                    graph[dep].add(pkg)
        if pkg not in graph:
            graph[pkg] = set()
    return graph


def reverse_graph(graph):
    """Reverse edges of the dependency graph."""
    rev = defaultdict(set)
    for src, targets in graph.items():
        for tgt in targets:
            rev[tgt].add(src)
    return rev


def get_all_dependencies(root, packages, include):
    """Recursively collect all dependencies for a root package."""
    visited = set()
    stack = [root]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for cat in include:
            for dep in packages.get(current, {}).get(cat, []):
                if dep not in visited:
                    stack.append(dep)
    return visited


def topological_sort(graph):
    """Return a topological order of nodes in a directed acyclic graph."""
    in_degree = {node: 0 for node in graph}
    for node, edges in graph.items():
        for neighbor in edges:
            in_degree[neighbor] += 1

    queue = deque([n for n in graph if in_degree[n] == 0])
    order = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in graph[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(graph):
        raise RuntimeError("Cycle detected in dependency graph")

    return order


def print_tree(pkg, packages, include, prefix="", seen=None):
    """Recursively print dependency tree for a given package."""
    if seen is None:
        seen = set()
    if pkg in seen:
        print(prefix + f"└── (circular) {pkg}")
        return
    seen.add(pkg)

    deps = packages.get(pkg, {})
    for i, cat in enumerate(include):
        items = deps.get(cat, [])
        if not items:
            continue
        print(f"{prefix}├── {cat}:")
        for dep in items:
            print(prefix + f"│   ├── {dep}")
            print_tree(dep, packages, include, prefix + "│   ", seen.copy())


def main():
    parser = argparse.ArgumentParser(description="YAML-based package dependency resolver")
    parser.add_argument("--path", required=True, help="Path to directory with package YAML files")
    parser.add_argument(
        "--include",
        type=str,
        default="required",
        help="Comma-separated dependency categories to include (e.g. 'required,recommended,optional,runtime')",
    )
    parser.add_argument("--roots", nargs="+", required=True, help="Root package(s) or '*' for all")
    parser.add_argument("--tree", action="store_true", help="Display dependency tree")
    parser.add_argument("--output", help="Write ordered build list to file")

    args = parser.parse_args()
    path = Path(args.path)

    include = [x.strip() for x in args.include.split(",") if x.strip()]

    print("[Dependency Resolver]")
    print(f"Included dependency types: {', '.join(args.include)}")

    packages = load_packages(path)
    all_pkg_names = list(packages.keys())

    # Determine root set
    if args.roots == ["*"]:
        roots = all_pkg_names
        print("Root packages: ALL")
    else:
        roots = args.roots
        print(f"Root packages: {', '.join(roots)}")

    # Build dependency graph
    graph = build_graph(packages, args.include)
    rev_graph = reverse_graph(graph)

    # Restrict to dependencies reachable from roots
    all_related = set()
    for root in roots:
        all_related |= get_all_dependencies(root, packages, args.include)
        all_related.add(root)

    subgraph = {n: {d for d in graph[n] if d in all_related} for n in all_related}

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
            print_tree(root, packages, args.include, prefix="  ")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)
