import copy
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

    WEIGHT_MAP = {"required": 1, "recommended": 2, "optional": 3}

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
        3) hardcoded ['required','recommended']
        """
        allowed = (
            self.dep_classes.get(node_id)
            or self.dep_classes.get("default")
            or ["required", "recommended"]
        )
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
                for dep_name in deps:
                    dep_id = self.name_to_id.get(dep_name)
                    if not dep_id:
                        self.warnings.append(
                            f"{section_id} depends on unknown package '{dep_name}'; skipping."
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

        # make edge order deterministic
        for sid in self.graph:
            self.graph[sid].sort(key=lambda t: (t[0], t[1], t[2]))

    def resolve_build_order(self) -> list[ParsedEntry]:
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
        """
        Transform qualifiers:
          - 'a' (after): reverse edge direction (X -a-> Y) ==> (Y -b-> X)
          - 'f' (first): create X-pass1 fence:
              * X -> X-pass1 (required, 'b')
              * X-pass1 -> Y for each original (X -f-> Y) (preserve weight, 'b')
              * For each non-first dep D of X: add D -> X-pass1 (required, 'b')
        All other edges keep qualifier 'b'. Edges are deduped and sorted.
        """
        # Work on a deep copy so caller's graph remains untouched
        out: dict[str, list[tuple[str, int, str]]] = {n: list(edges) for n, edges in graph.items()}
    
        def _add_node(nid: str):
            if nid not in out:
                out[nid] = []
    
        def _add_edge(src: str, dst: str, weight: int, qual: str = 'b'):
            _add_node(src); _add_node(dst)
            out[src].append((dst, weight, qual))
    
        # 1) Normalize: collect 'a' and 'f' edges; strip them from 'out'
        after_edges: list[tuple[str, str, int]] = []     # (X, Y, w) meaning X -a-> Y
        first_map: dict[str, list[tuple[str, int]]] = {} # X -> [(Y, w), ...]
    
        for x in list(out.keys()):
            new_list: list[tuple[str, int, str]] = []
            for (dep, w, q) in out.get(x, []):
                if q == 'a':
                    after_edges.append((x, dep, w))  # to be reversed
                elif q == 'f':
                    first_map.setdefault(x, []).append((dep, w))  # handled later
                else:
                    # keep 'b' (and any unknown treated as 'b' upstream)
                    new_list.append((dep, w, 'b'))
            out[x] = new_list
    
        # Ensure all nodes from original graph exist
        for n in graph:
            _add_node(n)
    
        # 2) Apply 'a' edges as reversed 'b' edges:  (X -a-> Y) ==> (Y -b-> X)
        for x, y, w in after_edges:
            _add_edge(y, x, w, 'b')
    
        # 3) Apply 'f' edges via fence nodes
        for x, f_deps in first_map.items():
            fence = f"{x}-pass1"
            _add_node(fence)
    
            # X depends on the fence (required)
            _add_edge(x, fence, 1, 'b')
    
            # Fence depends on every first dep (preserve weight)
            fset = set()
            for (y, w) in f_deps:
                _add_edge(fence, y, w, 'b')
                fset.add(y)
    
            # For each non-first dep D of X, force D to come after the fence:
            # encode as D depends on fence (required), so fence (and thus Y) precedes D.
            non_first_deps = [dep for (dep, _, _) in out.get(x, []) if dep not in fset and dep != fence]
            for d in non_first_deps:
                _add_edge(d, fence, 1, 'b')
    
        # 4) Deduplicate edges per node and sort deterministically
        for n, edges in out.items():
            # Use a set to dedupe; keep the *lowest* weight if duplicates exist
            best = {}
            for (dst, w, q) in edges:
                key = (dst, q)
                if key not in best or w < best[key]:
                    best[key] = w
            dedup = [(dst, w, q) for (dst, q), w in best.items()]
            dedup.sort(key=lambda t: (t[0], t[1], t[2]))
            out[n] = dedup
    
        return out

    def _pass3_topological_sort(self, graph: dict) -> list[str]:
        """
        DFS topo sort with simple cycle breaking (ignore back-edge) and one-time cycle reporting.
        """
        sorted_list: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()
        reported_cycles: set[tuple[str, str]] = set()

        def visit(nid: str):
            visiting.add(nid)
            for dep_id, _, _ in graph.get(nid, []):
                if dep_id in visiting:
                    key = tuple(sorted((nid, dep_id)))
                    if key not in reported_cycles:
                        self.warnings.append(f"Cycle detected: {nid} ↔ {dep_id}. Ignoring edge {nid}→{dep_id}.")
                        reported_cycles.add(key)
                    # skip the back-edge
                    continue
                if dep_id not in visited:
                    visit(dep_id)
            visiting.remove(nid)
            visited.add(nid)
            if nid != 'root':
                sorted_list.append(nid)

        for dep_id, _, _ in graph.get('root', []):
            if dep_id not in visited:
                visit(dep_id)

        # deterministic final order
        return sorted(sorted_list, key=lambda x: x)

