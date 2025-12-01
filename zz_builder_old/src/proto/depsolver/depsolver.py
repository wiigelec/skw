#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from collections import defaultdict, deque
import yaml, toml, json, argparse, sys


class DependencySolver:
    """
    DependencySolver v4.2
    Dual-build + runtime-aware rebuild model.
    """

    def __init__(self, target: str, yaml_dir: Path, alias_file: Path, include_classes: list[str]):
        self.target = target.lower()
        self.yaml_dir = Path(yaml_dir)
        self.alias_file = Path(alias_file)
        self.include_classes = include_classes
        self.alias_map = self._load_aliases()
        self.dependency_tree: dict[str, dict] = {}
        self.first_pass_set: set[str] = set()   # <-- track _first rebuilds

    # --------------------------------------------------------------
    # Loaders
    # --------------------------------------------------------------
    def _load_aliases(self) -> dict[str, str]:
        if not self.alias_file.exists():
            print(f"[ERROR] Alias file not found: {self.alias_file}")
            sys.exit(1)
        with open(self.alias_file, "r") as f:
            data = toml.load(f)
        aliases = data.get("aliases", {})
        return {k.lower(): v.strip() for k, v in aliases.items() if isinstance(v, str)}

    def _resolve_yaml_path(self, dep: str) -> tuple[Path | None, str | None]:
        """Return (yaml_path, canonical_name) for dependency, or (None, None) if skipped."""
        dep = dep.lower()
        if not dep:
            return None, None

        # 1. direct match
        candidates = []
        for f in self.yaml_dir.glob("*.yaml"):
            base = "-".join(f.stem.split("-")[:-1]) or f.stem
            if base.lower() == dep:
                candidates.append(f)
        if len(candidates) > 1:
            print(f"[ERROR] Multiple YAML files match dependency '{dep}': {[c.name for c in candidates]}")
            sys.exit(1)
        if len(candidates) == 1:
            return candidates[0], dep

        # 2. alias lookup
        if dep in self.alias_map:
            alias_value = self.alias_map[dep]
            if not alias_value:
                return None, None   # skip blank alias
            yaml_path = self.yaml_dir / f"{alias_value}.yaml"
            if not yaml_path.exists():
                print(f"[ERROR] Alias '{dep}' points to missing file '{yaml_path.name}'")
                sys.exit(1)
            canonical = alias_value.split("-")[0].lower()
            return yaml_path, canonical

        print(f"[ERROR] Missing YAML for dependency '{dep}'")
        sys.exit(1)

    def _parse_yaml(self, path: Path) -> dict:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}

    # --------------------------------------------------------------
    # Stage 1 – Collect Tree
    # --------------------------------------------------------------
    def _extract_filtered_dependencies(self, pkg_yaml: dict) -> dict[str, list[str]]:
        deps = pkg_yaml.get("dependencies", {})
        collected = {"first": [], "before": [], "after": []}

        for key, val in deps.items():
            if key.startswith("optional_"):
                continue
            if not any(key.startswith(cls + "_") for cls in self.include_classes):
                continue

            if key.endswith("_first"):
                group = "first"
            elif key.endswith("_before"):
                group = "before"
            elif key.endswith("_after"):
                group = "after"
            else:
                continue

            names = val.get("name") if isinstance(val, dict) else None
            if isinstance(names, str):
                names = [names]
            for n in names or []:
                if n and n.strip():
                    collected[group].append(n.lower())
                    if group == "first":
                        self.first_pass_set.add(n.lower())   # record rebuild

        return collected

    def _collect_dependencies(self, pkg_name: str, visited=None):
        if visited is None:
            visited = set()
        if pkg_name in visited:
            return
        visited.add(pkg_name)

        yaml_path, canon_name = self._resolve_yaml_path(pkg_name)
        if yaml_path is None:
            self.dependency_tree[pkg_name] = {"_warn": "Skipped blank alias"}
            return
        pkg_yaml = self._parse_yaml(yaml_path)
        deps = self._extract_filtered_dependencies(pkg_yaml)
        self.dependency_tree[canon_name] = deps

        for group in deps.values():
            for dep in group:
                self._collect_dependencies(dep, visited)

    def build_tree(self) -> dict:
        print(f"[INFO] Building dependency tree for target: {self.target}")
        self.dependency_tree.clear()
        self._collect_dependencies(self.target)
        return self.dependency_tree

    # --------------------------------------------------------------
    # Stage 2 – Graph + Unified Build List
    # --------------------------------------------------------------
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
        for n in graph:
            if n not in seen:
                order.append(n)
        return order

    def build_order(self) -> dict[str, list[str]]:
        build_edges = defaultdict(set)

        def add_edge(a, b):
            if b not in build_edges[a]:
                build_edges[a].add(b)

        def collect_edges(node, seen=None):
            if seen is None:
                seen = set()
            if node in seen:
                return
            seen.add(node)
            pkg_deps = self.dependency_tree.get(node, {"first": [], "before": [], "after": []})

            # recurse depth-first
            for group in pkg_deps.values():
                for dep in group:
                    collect_edges(dep, seen.copy())

            for dep in pkg_deps["before"]:
                add_edge(dep, node)
            for dep in pkg_deps["after"]:
                add_edge(node, dep)
            for dep in pkg_deps["first"]:
                add_edge(dep, node)
                add_edge(node, dep)
                print(f"[INFO] dual-build: {node} ↔ {dep}")

        collect_edges(self.target)
        for pkg in self.dependency_tree:
            build_edges.setdefault(pkg, set())

        build_order = self._topo_sort(build_edges)

        # Runtime order (reverse build)
        runtime_order = [p for p in reversed(build_order) if p != self.target]
        runtime_order.insert(0, self.target)

        # --- Stage 4.2 logic ---
        runtime_final = [
            pkg for pkg in runtime_order
            if pkg not in build_order or pkg in self.first_pass_set
        ]
        final_build_list = build_order + runtime_final

        return {
            "build_order": build_order,
            "runtime_order": runtime_order,
            "final_build_list": final_build_list,
        }

    # --------------------------------------------------------------
    # Output
    # --------------------------------------------------------------
    def print_tree(self):
        print(json.dumps(self.dependency_tree, indent=2))

    def print_order(self, data):
        print(json.dumps(data, indent=2))


# --------------------------------------------------------------
# CLI
# --------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Dependency Solver v4.2 (Runtime-Aware Rebuilds)")
    p.add_argument("--target", required=True)
    p.add_argument("--yaml-dir", required=True, type=Path)
    p.add_argument("--alias-file", required=True, type=Path)
    p.add_argument("--classes", nargs="+", default=["required", "recommended"])
    p.add_argument("--order", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()

    solver = DependencySolver(a.target, a.yaml_dir, a.alias_file, a.classes)
    tree = solver.build_tree()

    if a.order:
        data = solver.build_order()
        solver.print_order(data)
        if a.output:
            with open(a.output, "w") as f:
                json.dump(data, f, indent=2)
            print(f"[INFO] Build/runtime order saved to: {a.output}")
    else:
        solver.print_tree()
        if a.output:
            with open(a.output, "w") as f:
                json.dump(tree, f, indent=2)
            print(f"[INFO] Dependency tree saved to: {a.output}")


if __name__ == "__main__":
    main()
