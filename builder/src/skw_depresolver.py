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
    Dependency resolver using DFS stack traversal with strict priority order:
    required → recommended → optional → runtime.
    Cycle detection: raises RuntimeError when a cycle is found.
    """

    PRIORITY_ORDER = ["required", "recommended", "optional", "runtime"]

    def __init__(self,
                 parsed_entries: dict[str, ParsedEntry],
                 root_section_ids: list[str],
                 dep_classes: dict[str, list[str]]):
        self.parsed_entries = parsed_entries
        self.root_section_ids = root_section_ids
        self.dep_classes = dep_classes
        self.warnings: list[str] = []

    def resolve_build_order(self) -> list[ParsedEntry]:
        """Resolve dependencies into an ordered build list."""
        build_queue: list[str] = []
        visited: set[str] = set()
        stack: set[str] = set()

        for root_id in self.root_section_ids:
            if root_id not in self.parsed_entries:
                self.warnings.append(f"Requested root '{root_id}' not found; skipping.")
                continue
            self._resolve_package(root_id, build_queue, visited, stack)

        return [self.parsed_entries[sid] for sid in build_queue if sid in self.parsed_entries]

    def _resolve_package(self,
                         pkg_id: str,
                         build_queue: list[str],
                         visited: set[str],
                         stack: set[str]) -> None:
        """Depth-first resolution of one package and its dependencies."""
        if pkg_id in visited:
            return
        if pkg_id in stack:
            raise RuntimeError(f"Dependency cycle detected at '{pkg_id}'")

        stack.add(pkg_id)
        entry = self.parsed_entries.get(pkg_id)
        if not entry:
            self.warnings.append(f"Unknown package '{pkg_id}'; skipping.")
            stack.remove(pkg_id)
            return

        # Walk dependencies in flowchart order
        for dep_class in self.PRIORITY_ORDER:
            for dep in entry.dependencies.get(dep_class, []):
                self._resolve_package(dep, build_queue, visited, stack)

        # Finished with all deps → add package to build queue
        build_queue.append(pkg_id)
        visited.add(pkg_id)
        stack.remove(pkg_id)
