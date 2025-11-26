#!/usr/bin/env python3
import os
import argparse
import glob

class DepSolver:
    def __init__(self, dep_dir: str = "./dependencies"):
        """
        Initialize the dependency solver.
        Creates the dependency directory if it does not exist.
        """
        self.dep_dir = os.path.abspath(dep_dir)
        os.makedirs(self.dep_dir, exist_ok=True)

    def generate_deps(self, packages: list[str]):
        """
        Reimplementation of the Bash 'generate_deps()' function.

        - Clears all *.dep and *.tree files.
        - Creates root.dep with one line per package: '1 b <package>'.
        """
        dep_pattern = os.path.join(self.dep_dir, "*.{dep,tree}")
        # Remove old dependency and tree files
        for pattern in ["*.dep", "*.tree"]:
            for file in glob.glob(os.path.join(self.dep_dir, pattern)):
                try:
                    os.remove(file)
                except OSError as e:
                    print(f"Warning: could not remove {file}: {e}")

        root_path = os.path.join(self.dep_dir, "root.dep")

        # Write root.dep file
        with open(root_path, "w") as root_file:
            for pkg in packages:
                pkg = pkg.strip()
                if pkg:
                    root_file.write(f"1 b {pkg}\n")

        print(f"[OK] Created {root_path}")
        print(f"Root dependencies:")
        for pkg in packages:
            print(f"  1 b {pkg}")

def main():
    parser = argparse.ArgumentParser(
        description="Reimplementation of generate_deps() in Python"
    )
    parser.add_argument(
        "--packages",
        type=str,
        required=True,
        help="Comma-separated list of packages to include (e.g., --packages vim,wget,xorg)"
    )
    parser.add_argument(
        "--dep-dir",
        type=str,
        default="./dependencies",
        help="Directory where dependency files will be created"
    )

    args = parser.parse_args()
    packages = [p.strip() for p in args.packages.split(",") if p.strip()]

    solver = DepSolver(dep_dir=args.dep_dir)
    solver.generate_deps(packages)

if __name__ == "__main__":
    main()
