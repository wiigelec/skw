import copy
from collections import deque
from dataclasses import dataclass, field

# Define the ParsedEntry dataclass, as it's the expected output format.
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
    Resolves package dependencies based on a three-pass graph algorithm.

    This class implements the logic described in the func_dependencies script,
    translating its file-based graph manipulation into an in-memory process.
    It builds a subgraph of reachable nodes, transforms it to handle special
    dependency qualifiers, and performs a topological sort with cycle-breaking
    to produce a valid build order.
    """

    def __init__(self, parsed_entries: dict[str, ParsedEntry], root_section_ids: list[str], dep_classes: dict[str, list[str]]):
        self.parsed_entries = parsed_entries
        self.root_section_ids = root_section_ids
        self.dep_classes = dep_classes
        self.graph = {}
        self.reverse_graph = {} # To find parents easily

        # Maps dependency types to the integer weights used in the script.
        self.WEIGHT_MAP = {"required": 1, "recommended": 2, "optional": 3}
        self._build_initial_graph()

    def _build_initial_graph(self):
        """
        Converts the ParsedEntry objects into an internal graph representation.
        The graph is a dictionary where keys are package IDs and values are
        lists of (dependency_id, weight, qualifier) tuples.
        """
        # [cite_start]Create a special 'root' node for the user-requested packages [cite: 30]
        self.graph['root'] = []
        self.reverse_graph['root'] = []

        all_ids = set(self.parsed_entries.keys())
        for section_id in all_ids:
            self.graph.setdefault(section_id, [])
            self.reverse_graph.setdefault(section_id, [])

        for section_id, entry in self.parsed_entries.items():
            for dep_type, deps in entry.dependencies.items():
                weight = self.WEIGHT_MAP.get(dep_type)
                if not weight:
                    continue

                for dep_name in deps:
                    # The script implies dependencies are tracked by package name,
                    # which we map back to section_id.
                    dep_id = self._find_id_for_package_name(dep_name)
                    if dep_id and dep_id in all_ids:
                        # For now, all qualifiers are 'before' ('b') as a default
                        # [cite_start]The script's qualifiers are 'b', 'a', 'f' [cite: 32]
                        self.graph[section_id].append((dep_id, weight, 'b'))
                        self.reverse_graph.setdefault(dep_id, []).append(section_id)

        # [cite_start]Add edges from the root node to the user's requested packages [cite: 31]
        for root_id in self.root_section_ids:
            if root_id in self.graph:
                self.graph['root'].append((root_id, 1, 'b'))
                self.reverse_graph.setdefault(root_id, []).append('root')

    def _find_id_for_package_name(self, package_name: str) -> str | None:
        """Finds the section_id for a given package name."""
        for section_id, entry in self.parsed_entries.items():
            if entry.package_name == package_name:
                return section_id
        return None

    def resolve_build_order(self) -> list[ParsedEntry]:
        """
        Executes the full three-pass dependency resolution algorithm.
        """
        # [cite_start]Pass 1: Generate the subgraph of reachable nodes [cite: 25]
        reachable_graph, max_weights = self._pass1_generate_subgraph()

        # [cite_start]Pass 2: Transform the graph to handle special qualifiers [cite: 43]
        transformed_graph = self._pass2_transform_graph(reachable_graph)

        # [cite_start]Pass 3: Remove cycles and generate the topological sort [cite: 24]
        sorted_ids = self._pass3_topological_sort(transformed_graph)

        # Convert the final list of IDs back to ParsedEntry objects
        build_order = []
        for section_id in sorted_ids:
            if section_id in self.parsed_entries:
                build_order.append(self.parsed_entries[section_id])
            # Note: A full implementation would also handle entries for
            # newly created -pass1 and -groupxx nodes.

        return build_order

    def _pass1_generate_subgraph(self) -> tuple[dict, dict]:
        """
        Performs a traversal from the 'root' node to find all reachable
        [cite_start]packages, respecting the dependency weight limits. [cite: 22]
        """
        q = deque(['root'])
        reachable_nodes = {'root'}
        max_weights = {} # Store max weight allowed for each node's deps

        while q:
            node_id = q.popleft()
            
            # [cite_start]Determine max dependency level for this node. [cite: 79, 80]
            # The script uses DEP_LEVEL, mapped here via dep_classes config.
            allowed_classes = self.dep_classes.get(node_id, ['required', 'recommended'])
            max_weight = max(self.WEIGHT_MAP[c] for c in allowed_classes if c in self.WEIGHT_MAP)
            max_weights[node_id] = max_weight

            for dep_id, weight, qualifier in self.graph.get(node_id, []):
                if weight <= max_weight:
                    if dep_id not in reachable_nodes:
                        reachable_nodes.add(dep_id)
                        q.append(dep_id)

        # Create the subgraph containing only reachable nodes and their edges.
        subgraph = {node: [] for node in reachable_nodes}
        for node_id in reachable_nodes:
            if node_id in self.graph:
                 subgraph[node_id] = [
                    edge for edge in self.graph[node_id] if edge[0] in reachable_nodes
                ]
        return subgraph, max_weights

    def _pass2_transform_graph(self, graph: dict) -> dict:
        """
        In a full implementation, this pass would handle 'after' and 'first'
        [cite_start]qualifiers by modifying the graph structure. [cite: 51, 63]
        [cite_start]This stub simulates the removal of dangling edges. [cite: 46]
        """
        # Loop 1: Remove dangling edges (already done by subgraph creation)
        # Loop 2: Treat 'after' edges (not implemented in this stub)
        # Loop 3: Create '-pass1' nodes for 'first' edges (not implemented)
        print("INFO: Pass 2 (Graph Transformation) is a stub in this implementation.")
        return copy.deepcopy(graph) # Return a copy to modify in the next pass

    def _pass3_topological_sort(self, graph: dict) -> list[str]:
        """
        Performs a DFS-based topological sort, detecting and breaking cycles.
        This mirrors the logic in the 'generate_dependency_tree' function.
        """
        sorted_list = []
        # Path tracks nodes in the current recursion stack to detect cycles.
        path = set()
        # Visited tracks all nodes that have been fully processed.
        visited = set()

        def visit(node_id):
            path.add(node_id)
            visited.add(node_id)

            # [cite_start]Note: The script's cycle breaking is complex. [cite: 70, 148]
            # If A->B and B is on the current path, it's a cycle.
            # The script would prune the A->B edge if its weight is higher
            # than other weights in the cycle.
            # This simplified version just reports cycles.
            for dep_id, weight, qualifier in graph.get(node_id, []):
                if dep_id in path:
                    print(f"WARNING: Cycle detected involving {node_id} and {dep_id}. Simple sort will proceed.")
                    continue # Simple cycle breaking: ignore back-edge
                if dep_id not in visited:
                    visit(dep_id)

            path.remove(node_id)
            # Add the node to the front of the list (reverse topological order)
            if node_id != 'root':
                sorted_list.insert(0, node_id)

        # Start the sort from the 'root' node's dependencies.
        if 'root' in graph:
            # Sort initial dependencies to have a deterministic starting order
            root_deps = sorted(graph['root'])
            for dep_id, _, _ in root_deps:
                if dep_id not in visited:
                    visit(dep_id)

        return sorted_list
