from dataclasses import dataclass, field

# This dataclass is required for the stub to create the correct object types.
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
    A stub dependency resolver for testing purposes.
    
    This class mimics the interface of the real SKWDepResolver but returns a
    fixed, hardcoded list of packages instead of performing actual dependency
    resolution.
    """
    def __init__(self, parsed_entries: dict, root_section_ids: list, dep_classes: dict):
        """
        Initializes the resolver.
        
        Args:
            parsed_entries (dict): A dictionary of all parsed entries from the parser.
            root_section_ids (list): The list of starting sections for resolution.
            dep_classes (dict): A dictionary mapping section IDs to allowed dependency classes.
        """
        # In this stub, we don't need to use the inputs, but we accept them
        # to match the required interface.
        print("INFO: SKWDepResolver (Stub) initialized.")
        self.parsed_entries = parsed_entries
        self.root_section_ids = root_section_ids


    def resolve_build_order(self) -> list[ParsedEntry]:
        """
        Returns a hardcoded, ordered list of dummy ParsedEntry objects.
        
        Returns:
            list[ParsedEntry]: A short, static list representing a build plan.
        """
        print("INFO: SKWDepResolver (Stub) is returning a dummy build order.")
        
        # 🎯 Create a couple of dummy entries to return.
        # The order implies that 'binutils' must be built before 'gcc'.
        dummy_build_list = [
            ParsedEntry(
                source_book="lfs-12.1",
                chapter_id="chapter08",
                section_id="binutils-pass1",
                package_name="binutils",
                package_version="2.41",
                sources={
                    "urls": ["https://ftp.gnu.org/gnu/binutils/binutils-2.41.tar.xz"],
                    "checksums": ["e81365637d591b83594b7911afd13ce633393ad8a57e3f65e2b0532252a1c0b3"]
                },
                dependencies={"required": [], "optional": []},
                build_instructions=[
                    "mkdir -v build",
                    "cd build",
                    "../configure --prefix=$LFS/tools ...",
                    "make",
                    "make install"
                ]
            ),
            ParsedEntry(
                source_book="lfs-12.1",
                chapter_id="chapter08",
                section_id="gcc-pass1",
                package_name="gcc",
                package_version="13.2.0",
                sources={
                    "urls": ["https://ftp.gnu.org/gnu/gcc/gcc-13.2.0/gcc-13.2.0.tar.xz"],
                    "checksums": ["a4726b1c6e1b3877990473954502f23235b644a982d627c284478832a85376a2"]
                },
                dependencies={"required": ["binutils-pass1"], "optional": []},
                build_instructions=[
                    "tar -xf ../mpfr-4.2.0.tar.xz",
                    "mv -v mpfr-4.2.0 mpfr",
                    "./configure --prefix=$LFS/tools ...",
                    "make",
                    "make install"
                ]
            )
        ]
        
        return dummy_build_list
