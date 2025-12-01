#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque
import yaml
import toml
import json
import argparse
import sys


class DependencySolver:
    """
    DependencySolver v3.0
    - Depth-first DAG builder
    - Correct edge direction (dep → dependent)
    - Merges runtime + build sequences into final_build_list
    """

    def __init__(self, target: str, yaml_dir: Path, alias_file: Path, include_classes: list[str]):
        self.target = target.lower()
        self.yaml_dir = Path(yaml_dir)
        self.alias_file = Path(alias_file)
        self.include_classes = include_classes
        self.alias_map = self._load_aliases()
        self.dependency_tree: dict[str, dict] = {}

    # ----------------------------------------------------------------
    # Loaders
    # ----------------------------------------------------------------
    def _load_aliases(self) -> dict[str, str]:
        if not self.alias_file.exists():
            print(f"[ERROR] Alias file not found: {self.alias_file}")
            sys.exit(1)
        with open(self.alias_file, "r") as f:
            data = toml.load(f)
        aliases = data.get("aliases", {})
        return {k.lower(): v.strip() for k, v in aliases.items() if isinstance(v, str)}

    def _resolve_yaml_path(self, dep: str) -> Path | None:
        dep = dep.lower()
        if not dep:
            return None
        candidates = []
        for f in self.yaml_dir.glob("*.yaml"):
            parts = f.stem.split("-")
            base = "-".join(parts[:-1]) if len(parts) > 1 else f.stem
            if base.lower() == dep:
                candidates.append(f)
        if len(candidates) > 1:
            print(f"[ERROR] Multiple YAML files match dependency '{dep}': {[c.name for c in candidates]}")
            sys.exit(1)
        if len(candidates) == 1:
            return candidates[0]
        if dep in self.alias_map:
            alias_value = self.alias_map[dep]
            if not alias_value:
                return None  # silently skip blank alias
            yaml_path = self.yaml_dir / f"{alias_value}.yaml"
            if not yaml_path.exists():
                print(f"[ERROR] Alias '{dep}' points to missing file '{yaml_path.name}'")
                sys.exit(1)
            return yaml_path
        print(f"[ERROR] No YAML or alias found for dependency '{dep}'")
        sys.exit(1)

    def _parse_yaml(self, path: Path) -> dict:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}

    # ----------------------------------------------------------------
    # Stage 1 — Dependency Tree
    # ----------------------------------------------------------------
    def _extract_filtered_dependencies(self, pkg_yaml: dict) -> list[str]:
        deps = pkg_yaml.get("dependencies", {})
        result = set()
        for key, val in deps.items():
            if key.startswith("required_") or key.startswith("recommended_") or (
                key.endswith("_after")
                and (key.startswith("required_") or key.startswith("recommended_"))
            ):
                if isinstance(val, dict) and "name" in val:
                    names = val["name"]
                    if isinstance(names, str):
                        result.add(names.lower())
                    elif isinstance(names, list):
                        result.update([n.lower() for n in names if n])
        # silently drop blanks
        return sorted({d.strip() for d in result if d and d.strip()})

    def _collect_dependencies(self, pkg_name: str, visited=None) -> None:
        if visited is None:
            visited = set()
        if pkg_name in visited:
            return
        visited.add(pkg_name)
        yaml_path = self._resolve_yaml_path(pkg_name)
        if yaml_path is None:
            self.dependency_tree[pkg_name] = {"_warn": "Skipped due to blank alias"}
            return
        pkg_yaml = self._parse_yaml(yaml_path)
        deps = self._extract_filtered_dependencies(pkg_yaml)
        self.dependency_tree[pkg_name] = deps
        for dep in deps:
            self._collect_dependencies(dep, visited)

    def build_tree(self) -> dict:
        print(f"[INFO] Building dependency tree for target: {self.target}")
        self.dependency_tree.clear()
        self._collect_dependencies(self.target)
        return self.dependency_tree

    # ----------------------------------------------------------------
    # Stage 2 — Graph + Unified Build List
    # ----------------------------------------------------------------
    def _topo_sort(self, graph: dict[str, set[str]]) -> list[str]:
        indeg = defaultdict(int)
        for u in graph:
            for v in graph[u]:
                indeg[v] += 1
        queue = deque([u for u in graph if indeg[u] == 0])
        order, seen = [], set()
        while queue:
            u = queue.popleft()
            if u in seen:
                continue
            seen.add(u)
            order.append(u)
            for v in graph[u]:
                indeg[v] -= 1
                if indeg[v] == 0:
                    queue.append(v)
        # Flatten circulars if any remain
        for n in graph:
            if n not in seen:
                order.append(n)
        return order

    def build_order(self) -> dict[str, list[str]]:
        build_edges = defaultdict(set)

        def add_edge(graph, a, b):
            if b not in graph[a]:
                graph[a].add(b)

        def collect_edges(node, seen=None):
            """Depth-first traversal ensures dependencies come first."""
            if seen is None:
                seen = set()
            if node in seen:
                return
            seen.add(node)
            for dep in self.dependency_tree.get(node, []):
                collect_edges(dep, seen.copy())
                add_edge(build_edges, dep, node)  # dependency → dependent

        collect_edges(self.target)
        for pkg in self.dependency_tree:
            if pkg not in build_edges:
                build_edges[pkg] = set()

        build_order = self._topo_sort(build_edges)
        runtime_order = [p for p in reversed(build_order) if p != self.target]
        runtime_order.insert(0, self.target)

        # Merge runtime packages not already built
        final_build_list = build_order.copy()
        for pkg in runtime_order:
            if pkg not in build_order:
                final_build_list.append(pkg)

        return {
            "build_order": build_order,
            "runtime_order": runtime_order,
            "final_build_list": final_build_list,
        }

    # ----------------------------------------------------------------
    # Output
    # ----------------------------------------------------------------
    def print_tree(self):
        print(json.dumps(self.dependency_tree, indent=2))

    def print_order(self, order_data):
        print(json.dumps(order_data, indent=2))


# --------------------------------------------------------------------
# CLI Entrypoint
# --------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Dependency Solver (Unified Build Sequence)")
    parser.add_argument("--target", required=True, help="Target package (e.g., systemd)")
    parser.add_argument("--yaml-dir", required=True, type=Path, help="Directory containing package YAMLs")
    parser.add_argument("--alias-file", required=True, type=Path, help="Alias mapping TOML file")
    parser.add_argument("--classes", nargs="+", default=["required", "recommended"],
                        help="Dependency classes to include")
    parser.add_argument("--order", action="store_true", help="Generate unified build/runtime order")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")

    args = parser.parse_args()
    solver = DependencySolver(args.target, args.yaml_dir, args.alias_file, args.classes)
    tree = solver.build_tree()

    if args.order:
        order_data = solver.build_order()
        solver.print_order(order_data)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(order_data, f, indent=2)
            print(f"[INFO] Build/runtime order saved to: {args.output}")
    else:
        solver.print_tree()
        if args.output:
            with open(args.output, "w") as f:
                json.dump(tree, f, indent=2)
            print(f"[INFO] Dependency tree saved to: {args.output}")


if __name__ == "__main__":
    main()
