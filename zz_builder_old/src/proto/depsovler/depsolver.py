import argparse
import yaml
from pathlib import Path
import networkx as nx

class SKWDepSolver:
    def __init__(self, yaml_dir, output_dir="dependencies", packages=None, classes=None, debug=False):
        self.yaml_dir = Path(yaml_dir)
        self.output_dir = Path(output_dir)
        self.packages = set(packages or [])
        self.classes = set(classes or ["required", "recommended", "optional"])
        self.graph = nx.DiGraph()
        self.weight_map = {"required": 1, "recommended": 2, "optional": 3}
        self.visited = set()
        self.debug = debug

    def _log(self, message):
        if self.debug:
            print(f"[DEBUG] {message}")

    def _find_yaml_file(self, pkg_name):
        exact = self.yaml_dir / f"{pkg_name}.yaml"
        if exact.exists():
            return exact

        matches = sorted(self.yaml_dir.glob(f"{pkg_name}-*.yaml"))
        if matches:
            self._log(f"Matched versioned YAML for {pkg_name}: {matches[0].name}")
            return matches[0]

        self._log(f"No YAML found for {pkg_name}")
        return None

    def _load_package_yaml(self, pkg_name):
        yaml_file = self._find_yaml_file(pkg_name)
        if not yaml_file or pkg_name in self.visited:
            self._log(f"Skipping {pkg_name} (already visited or missing YAML)")
            return

        self.visited.add(pkg_name)
        self._log(f"Loading {pkg_name} from {yaml_file}")

        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        deps = data.get("dependencies", {})
        if not deps:
            self._log(f"No dependencies for {pkg_name}")
            return

        for dep_type in self.classes:
            group = deps.get(dep_type, {})

            if isinstance(group, list):
                deps_iter = group
            else:
                deps_iter = []
                for order in ["first", "before", "after"]:
                    values = group.get(order, []) if isinstance(group, dict) else []
                    if isinstance(values, str):
                        values = [values]
                    deps_iter.extend([(v, order) for v in values])

            for item in deps_iter:
                if isinstance(item, tuple):
                    dep, qualifier = item
                else:
                    dep, qualifier = item, "before"
                if dep:
                    weight = self.weight_map.get(dep_type, 3)
                    self.graph.add_edge(pkg_name, dep, weight=weight, qualifier=qualifier)
                    self._log(f"Edge added: {pkg_name} -> {dep} ({qualifier}, weight={weight})")
                    self._load_package_yaml(dep)

    def load_yaml_files(self):
        for pkg in (self.packages or []):
            self._load_package_yaml(pkg)

    def handle_after_edges(self):
        after_edges = [(u, v) for u, v, d in self.graph.edges(data=True) if d.get("qualifier") == "after"]

        for u, v in after_edges:
            group_node = f"{v}-groupxx"

            if group_node not in self.graph:
                self.graph.add_node(group_node)

            for pred in list(self.graph.predecessors(u)):
                if pred != group_node:
                    self.graph.add_edge(pred, group_node, weight=1)

            self.graph.add_edge(group_node, v, weight=1)

            for child in list(self.graph.successors(v)):
                if child != group_node:
                    self.graph.add_edge(group_node, child, weight=self.graph[v][child].get("weight", 1))

            self.graph.remove_edge(u, v)

    def detect_and_resolve_cycles(self):
        cycles = list(nx.simple_cycles(self.graph))
        resolved = []

        for cycle in sorted(cycles, key=lambda c: tuple(sorted(c))):
            if len(cycle) < 2:
                continue

            cycle = sorted(cycle)
            edges = [(cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle))]
            existing_edges = [(u, v) for (u, v) in edges if self.graph.has_edge(u, v)]
            if not existing_edges:
                continue

            weights = [self.graph[u][v].get("weight", 3) for u, v in existing_edges]
            all_required = all(w == 1 for w in weights)

            if all_required:
                first = cycle[0]
                new_node = f"{first}-pass1"
                print(f"[CYCLE] Breaking required cycle {cycle} by adding {new_node}")

                self.graph.add_node(new_node)
                for pred in list(self.graph.predecessors(first)):
                    if pred not in cycle:
                        self.graph.add_edge(pred, new_node, weight=1)
                resolved.append((cycle, new_node))

                u, v = existing_edges[0]
                if self.graph.has_edge(u, v):
                    self.graph.remove_edge(u, v)
            else:
                weakest = max(existing_edges, key=lambda e: self.graph[e[0]][e[1]].get("weight", 3))
                u, v = weakest
                if self.graph.has_edge(u, v):
                    w = self.graph[u][v]["weight"]
                    print(f"[CYCLE] Dropping weaker edge {u} -> {v} (weight={w}) from cycle {cycle}")
                    self.graph.remove_edge(u, v)
                    resolved.append((cycle, f"dropped {u}->{v}"))

        return resolved

    def topological_sort(self):
        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXUnfeasible:
            print("[ERROR] Graph still contains cycles!")
            print("[DEBUG] Remaining cycles:")
            for c in nx.simple_cycles(self.graph):
                print("   ", " → ".join(c))
            return []

    def write_dep_files(self):
        self.output_dir.mkdir(exist_ok=True)
        for pkg in self.graph.nodes:
            out_file = self.output_dir / f"{pkg}.dep"
            with open(out_file, "w", encoding="utf-8") as f:
                for dep in self.graph.successors(pkg):
                    weight = self.graph[pkg][dep].get("weight", 3)
                    f.write(f"{weight} b {dep}\n")

    @classmethod
    def cli(cls):
        parser = argparse.ArgumentParser(description="Dependency solver for BLFS YAML build metadata.")
        parser.add_argument("yaml_dir", help="Directory containing YAML package metadata.")
        parser.add_argument("--packages", nargs="*", default=None, help="Specific packages to include.")
        parser.add_argument("--classes", nargs="*", choices=["required", "recommended", "optional"], default=["required", "recommended", "optional"], help="Dependency classes to include.")
        parser.add_argument("--output", default="dependencies", help="Output directory for .dep files.")
        parser.add_argument("--show-order", action="store_true", help="Print topological build order.")
        parser.add_argument("--debug", action="store_true", help="Enable debug output for detailed graph building.")

        args = parser.parse_args()
        solver = cls(args.yaml_dir, args.output, args.packages, args.classes, args.debug)
        solver.load_yaml_files()
        solver.handle_after_edges()
        print(f"[INFO] Loaded YAML metadata from {solver.yaml_dir}")

        cycles = solver.detect_and_resolve_cycles()
        if cycles:
            print(f"[INFO] Resolved {len(cycles)} circular dependency cycles.")

        order = solver.topological_sort()
        solver.write_dep_files()
        print(f"[INFO] .dep files written to {solver.output_dir}")

        if args.show_order and order:
            print("\nTopological Build Order:")
            for pkg in order:
                print(pkg)

if __name__ == "__main__":
    SKWDepSolver.cli()