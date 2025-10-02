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
    required ? recommended ? optional ? runtime.
    Cycle detection: raises RuntimeError with full cycle path when found.
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
        stack: list[str] = []  # switched to list everywhere

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
                         stack: list[str]) -> None:
        """Depth-first resolution of one package and its dependencies."""
        if pkg_id in visited:
            return
        if pkg_id in stack:
            cycle_start = stack.index(pkg_id)
            cycle_path = stack[cycle_start:] + [pkg_id]
            raise RuntimeError("Dependency cycle detected: " + " -> ".join(cycle_path))

        stack.append(pkg_id)
        entry = self.parsed_entries.get(pkg_id)
        if not entry:
            self.warnings.append(f"Unknown package '{pkg_id}'; skipping.")
            stack.pop()
            return

        # Walk dependencies in strict priority order
        for dep_class in self.PRIORITY_ORDER:
            for dep in entry.dependencies.get(dep_class, []):
                self._resolve_package(dep, build_queue, visited, stack)

        # Finished with all deps ? add package to build queue
        build_queue.append(pkg_id)
        visited.add(pkg_id)
        stack.pop()
