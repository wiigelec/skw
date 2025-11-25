#!/usr/bin/env python3
from pathlib import Path
import yaml
import sys
import argparse

# ==== Global settings ====
SPACE_STR = " " * 70
DEP_LEVEL = 3
MAIL_SERVER = "postfix"
RED, GREEN, YELLOW, MAGENTA, CYAN, OFF = "\033[31m", "\033[32m", "\033[33m", "\033[35m", "\033[36m", "\033[0m"

# ==== Parse YAML dependencies ====
def parse_yaml_dependencies(pkg_name: str, yaml_dir: Path) -> list[dict]:
    yaml_path = yaml_dir / f"{pkg_name}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML file not found for package: {pkg_name} ({yaml_path})")

    with yaml_path.open("r") as f:
        data = yaml.safe_load(f)

    deps = []
    dep_tree = data.get("dependencies", {})
    if not dep_tree:
        return deps

    mapping = {
        "required": 1,
        "recommended": 2,
        "optional": 3,
        "external": 4,
    }

    for level, weight in mapping.items():
        for qualifier in ["first", "before", "after", "external"]:
            key = f"{level}_{qualifier}"
            if key not in dep_tree:
                continue
            names = dep_tree[key].get("name", [])
            if not names:
                continue
            if isinstance(names, str):
                names = [names]
            q = qualifier[0] if qualifier != "external" else "b"
            for n in names:
                deps.append({"weight": weight, "qualifier": q, "target": n})
    return deps


# ==== Recursive dependency generator ====
def generate_subgraph(dep_file: Path, weight: int, depth: int, qualifier: str, yaml_dir: Path, dep_level: int):
    spacing = 1 if depth < 10 else 0
    priostring = {1: "required", 2: "recommended", 3: "optional"}.get(weight, "")
    buildstring = "runtime" if qualifier == "a" else ""
    print(f"\nNode: {depth}{SPACE_STR[:depth+spacing]}{RED}{dep_file.stem}{OFF} {priostring} {buildstring}")

    pkg_name = dep_file.stem
    try:
        dependencies = parse_yaml_dependencies(pkg_name, yaml_dir)
    except FileNotFoundError as e:
        print(f"{YELLOW}ERROR:{OFF} {e}")
        return 1

    with dep_file.open("w") as f:
        for dep in dependencies:
            f.write(f"{dep['weight']} {dep['qualifier']} {dep['target']}\n")

    for dep in dependencies:
        if dep["weight"] > dep_level:
            print(f"\n Out: {depth}{SPACE_STR[:depth+spacing]}{YELLOW}{dep['target']}{OFF} "
                  f"{priostring} {buildstring}")
            continue

        dep_path = dep_file.parent / f"{dep['target']}.dep"
        if dep_path.exists():
            print(f"\nEdge: {depth}{SPACE_STR[:depth+spacing]}{MAGENTA}{dep['target']}{OFF} "
                  f"{priostring} {buildstring}")
            continue

        sub_deps = parse_yaml_dependencies(dep["target"], yaml_dir)
        if not sub_deps:
            dep_path.touch()
            print(f"\nLeaf: {depth}{SPACE_STR[:depth+spacing]}{CYAN}{dep['target']}{OFF} "
                  f"{priostring} {buildstring}")
        else:
            generate_subgraph(dep_path, dep["weight"], depth + 1, dep["qualifier"], yaml_dir, dep_level)

    print(f"\n End: {depth}{SPACE_STR[:depth+spacing]}{GREEN}{dep_file.stem}{OFF}")
    return 0


# ==== Command Line Interface ====
def main():
    parser = argparse.ArgumentParser(
        description="Generate dependency .dep files from a directory of YAML package definitions."
    )
    parser.add_argument("root_package", help="Name of the root package (without .yaml extension)")
    parser.add_argument(
        "-y", "--yaml-dir",
        default="packages",
        help="Directory containing package YAML files (default: ./packages)"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="deps",
        help="Directory to store generated .dep files (default: ./deps)"
    )
    parser.add_argument(
        "-l", "--level",
        type=int,
        choices=[1, 2, 3, 4],
        default=DEP_LEVEL,
        help="Dependency level: 1=required, 2=recommended, 3=optional, 4=external"
    )

    args = parser.parse_args()
    yaml_dir = Path(args.yaml_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    root_dep_file = output_dir / f"{args.root_package}.dep"
    print(f"Generating subgraph for root package: {args.root_package}")
    result = generate_subgraph(root_dep_file, 1, 1, "b", yaml_dir, args.level)

    if result == 0:
        print(f"\n{GREEN}Dependency graph generation completed successfully.{OFF}")
    else:
        print(f"\n{YELLOW}Graph generation finished with warnings/errors.{OFF}")


if __name__ == "__main__":
    main()
