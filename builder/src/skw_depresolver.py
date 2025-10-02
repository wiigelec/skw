import copy
import heapq
from collections import deque
from dataclasses import dataclass, field

@dataclass
class ParsedEntry:
    source_book: str
    chapter_id: str
    section_id: str
    package_name: str
    package_version: str
    sources: dict = field(default_factory=dict)
    dependencies: dict = field(default_factory=dict)
    build_instructions: list = field(default_factory=list)


class SKWDepResolver:
    """
    Three-pass dependency resolver (reachable subgraph → qualifier transform → topo sort).
    Pass 2 remains a stub; it currently only preserves pass-1 structure.
    """

    WEIGHT_MAP = {"required": 1, "recommended": 2, "optional": 3, "external": 4, "runtime": 3}

    def __init__(self, parsed_entries: dict[str, ParsedEntry],
                 root_section_ids: list[str],
                 dep_classes: dict[str, list[str]]):
        self.parsed_entries = parsed_entries
        self.root_section_ids = root_section_ids
        self.dep_classes = dep_classes
        self.graph: dict[str, list[tuple[str, int, str]]] = {}
        self.reverse_graph: dict[str, list[str]] = {}
        # Fast lookup for package name → section_id
        self.name_to_id = {e.package_name: sid for sid, e in parsed_entries.items()}
        # Collect diagnostics for callers
        self.warnings: list[str] = []
        self._build_initial_graph()

    def _max_weight_for(self, node_id: str) -> int:
        """
        Resolve the max dependency level for a node. Priority:
        1) explicit node entry in dep_classes
        2) 'default' in dep_classes
        3) hardcoded [] (no dependencies)
        """
        # Add a special exception for the 'root' node
        if node_id == 'root':
            return 1 # Always allow the root to reach the requested packages
            
        allowed = (
            self.dep_classes.get(node_id)
            or self.dep_classes.get("default")
            or []
        )
        if not allowed:
            return 0  # A max weight of 0 means no dependencies will be followed
        return max(self.WEIGHT_MAP[c] for c in allowed if c in self.WEIGHT_MAP)

    def _build_initial_graph(self):
        # seed nodes
        self.graph['root'] = []
        self.reverse_graph['root'] = []
        for sid in self.parsed_entries:
            self.graph.setdefault(sid, [])
            self.reverse_graph.setdefault(sid, [])

        # package edges
        for section_id, entry in self.parsed_entries.items():
            for dep_type, deps in entry.dependencies.items():
                weight = self.WEIGHT_MAP.get(dep_type)
                if weight is None:
                    self.warnings.append(
                        f"Unknown dependency class '{dep_type}' in {section_id}; skipping."
                    )
                    continue
                for dep_id in deps:
                    if dep_id not in self.graph:
                        self.warnings.append(
                            f"{section_id} depends on unknown package '{dep_id}'; skipping."
                        )
                        continue
                    # default qualifier 'b' (before)
                    self.graph[section_id].append((dep_id, weight, 'b'))
                    self.reverse_graph[dep_id].append(section_id)

        # edges from root to requested packages
        for root_id in self.root_section_ids:
            if root_id in self.graph:
                self.graph['root'].append((root_id, 1, 'b'))
                self.reverse_graph[root_id].append('root')
            else:
                self.warnings.append(f"Requested root '{root_id}' not found; skipping.")

    def resolve_build_order(self) -> list[ParsedEntry]:
        # Fast-path: if no dependencies exist, just return the requested roots
        if all(not entry.dependencies for entry in self.parsed_entries.values()):
            return [
                self.parsed_entries[sid]
                for sid in self.root_section_ids
                if sid in self.parsed_entries
            ]
    
        # Otherwise run the full 3-pass resolution
        reachable_graph = self._pass1_generate_subgraph()
        transformed_graph = self._pass2_transform_graph(reachable_graph)
        sorted_ids = self._pass3_topological_sort(transformed_graph)
        return [self.parsed_entries[sid] for sid in sorted_ids if sid in self.parsed_entries]

    def _pass1_generate_subgraph(self) -> dict[str, list[tuple[str, int, str]]]:
        """
        BFS from 'root', respecting each node's max dependency level.
        """
        q = deque(['root'])
        reachable = {'root'}

        while q:
            node_id = q.popleft()
            max_weight = self._max_weight_for(node_id)
            for dep_id, weight, _ in self.graph.get(node_id, []):
                if weight <= max_weight and dep_id not in reachable:
                    reachable.add(dep_id)
                    q.append(dep_id)

        subgraph = {nid: [] for nid in reachable}
        for nid in reachable:
            subgraph[nid] = [e for e in self.graph.get(nid, []) if e[0] in reachable]
        return subgraph

    def _pass2_transform_graph(self, graph: dict[str, list[tuple[str, int, str]]]) -> dict[str, list[tuple[str, int, str]]]:
        out = {n: list(edges) for n, edges in graph.items()}
    
        def _add_edge(src, dst, w, q='b'):
            out.setdefault(src, []).append((dst, w, q))
    
        # Collect after and first edges
        after_edges = []
        first_map = {}
        for x, edges in list(out.items()):
            keep = []
            for (dep, w, q) in edges:
                if q == 'a':
                    after_edges.append((x, dep, w))
                elif q == 'f':
                    first_map.setdefault(x, []).append((dep, w))
                else:
                    keep.append((dep, w, 'b'))
            out[x] = keep
    
        # Promote 'after' edges upward
        for x, y, w in after_edges:
            for parent, edges in out.items():
                if any(dep == x for dep, _, _ in edges):
                    _add_edge(parent, y, w, 'b')
    
        # Handle 'first' edges with fence nodes
        for x, f_deps in first_map.items():
            fence = f"{x}-pass1"
            _add_edge(x, fence, 1, 'b')
            fset = set()
            for (y, w) in f_deps:
                _add_edge(fence, y, w, 'b')
                fset.add(y)
            for dep, _, _ in out.get(x, []):
                if dep not in fset and dep != fence:
                    _add_edge(dep, fence, 1, 'b')
    
        # Deduplicate edges
        for n, edges in out.items():
            best = {}
            for (dst, w, q) in edges:
                key = (dst, q)
                if key not in best or w < best[key]:
                    best[key] = w
            out[n] = [(dst, w, q) for (dst, q), w in best.items()]
    
        return out
    
    def _pass3_topological_sort(self, graph: dict[str, list[tuple[str, int, str]]]) -> list[str]:
        """
        Topological sort with global cycle pruning.
        - Uses a min-heap (heapq) to process nodes in ascending edge-weight order,
          so required < recommended < optional < external.
        - If cycles remain, prune the globally weakest edge and retry.
        """
        import heapq
    
        while True:
            # Compute indegree of each node
            indegree = {n: 0 for n in graph}
            for edges in graph.values():
                for (dst, _, _) in edges:
                    indegree[dst] = indegree.get(dst, 0) + 1
    
            # Initialize heap with nodes of indegree 0
            q = []
            for n, d in indegree.items():
                if d == 0:
                    heapq.heappush(q, (0, n))  # root-level nodes get weight 0
    
            order = []
            visited = set()
    
            while q:
                _, n = heapq.heappop(q)
                if n != 'root':
                    order.append(n)
                visited.add(n)
    
                # Process outgoing edges, sorted by weight
                for (dst, w, _) in sorted(graph.get(n, []), key=lambda e: e[1]):
                    indegree[dst] -= 1
                    if indegree[dst] == 0:
                        heapq.heappush(q, (w, dst))
    
            # Success: all nodes visited
            if len(visited) == len(graph):
                return order[::-1]
    
            # Cycle detected: prune weakest edge globally
            weakest = None
            for src, edges in graph.items():
                for (dst, w, q) in edges:
                    if weakest is None or w > weakest[2]:
                        weakest = (src, dst, w)
    
            if weakest:
                src, dst, _ = weakest
                graph[src] = [(d, w, q) for (d, w, q) in graph[src] if d != dst]
                self.warnings.append(f"Pruned edge {src} -> {dst} to break cycle.")
            else:
                break  # No edges left, fallback
    
        return order
