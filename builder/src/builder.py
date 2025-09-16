#!/usr/bin/env python3
import argparse
import os
import shutil
import sys
import tomllib  # Python 3.11+
import subprocess

class Builder:
    def __init__(self):
        self.skel_dir = "src/config/skel"
        self.builder_config = "config/builder.toml"

    # -------------------------------
    # Core setup
    # -------------------------------
    def configure(self):
        if os.path.exists(self.builder_config):
            print("builder.toml already exists. Please review manually.")
            return
        os.makedirs("config", exist_ok=True)
        shutil.copy(f"{self.skel_dir}/builder.toml.skel", self.builder_config)
        print(f"Initialized builder.toml at {self.builder_config}")
        with open(self.builder_config, "r", encoding="utf-8") as f:
            print(f.read())

    def _get_build_dir(self):
        if not os.path.exists(self.builder_config):
            sys.exit("Error: builder.toml not found. Run 'skw-build configure' first.")
        with open(self.builder_config, "rb") as f:
            cfg = tomllib.load(f)
        build_dir = cfg.get("dir_paths", {}).get("build_dir")
        if not build_dir:
            sys.exit("Error: 'build_dir' not set in builder.toml.")
        return build_dir

    # -------------------------------
    # Book management
    # -------------------------------
    def add_book(self, name):
        build_dir = self._get_build_dir()
        book_path = os.path.join(build_dir, "books", name, "config")
        os.makedirs(book_path, exist_ok=True)
        shutil.copy(
            f"{self.skel_dir}/book.toml.skel",
            os.path.join(book_path, "book.toml"),
        )
        print(f"Book '{name}' added.")
        with open(os.path.join(book_path, "book.toml"), "r", encoding="utf-8") as f:
            print(f.read())

    def list_books(self):
        build_dir = self._get_build_dir()
        books_dir = os.path.join(build_dir, "books")
        if not os.path.exists(books_dir):
            print("No books found.")
            return
        books = [d for d in os.listdir(books_dir) if os.path.isdir(os.path.join(books_dir, d))]
        if books:
            print("Books:")
            for b in books:
                print(f"  - {b}")
        else:
            print("No books found.")

    def install_book(self, book):
        """Clone or update a book repo, checkout version, and build XML"""
        build_dir = self._get_build_dir()
        book_config = os.path.join(build_dir, "books", book, "config", "book.toml")
        if not os.path.exists(book_config):
            sys.exit(f"Error: book.toml not found for book '{book}'. Did you run add-book?")

        # Load book config
        with open(book_config, "rb") as f:
            cfg = tomllib.load(f)
        repo_path = cfg["main"]["repo_path"]
        version = cfg["main"]["version"]
        rev = cfg["main"]["rev"]
        make_command = cfg["main"]["make_command"]
        output_file = cfg["main"]["output_file"]

        # Paths
        repo_dir = os.path.join(build_dir, "books", book, "repo")
        xml_output = os.path.join(build_dir, "books", book, output_file)

        # Clone if missing
        if not os.path.exists(repo_dir):
            print(f"Cloning {repo_path} into {repo_dir}")
            subprocess.run(["git", "clone", repo_path, repo_dir], check=True)
        else:
            print(f"Updating existing repo at {repo_dir}")
            subprocess.run(["git", "-C", repo_dir, "fetch", "--all"], check=True)

        # Checkout version
        print(f"Checking out {version}")
        subprocess.run(["git", "-C", repo_dir, "checkout", version], check=True)
        subprocess.run(["git", "-C", repo_dir, "pull"], check=True)

        # Prepare substitutions
        cwd = os.getcwd()
        substitutions = {
            "${book_dir}": os.path.join(cwd,build_dir, "books", book),
            "${rev}": rev,
        }

        # Replace placeholders in make_command
        for key, value in substitutions.items():
            make_command = make_command.replace(key, value)
            
        # Run make command with substitutions
        print(f"Running make command: {make_command}")

        # Run in repo directory
        subprocess.run(make_command, cwd=repo_dir, shell=True, check=True)

        # Verify output file exists
        if os.path.exists(xml_output):
            print(f"Book XML generated: {xml_output}")
        else:
            print(f"Warning: expected XML {output_file} not found in {build_dir}/books/{book}")

    # -------------------------------
    # Profile management
    # -------------------------------
    def add_profile(self, book, profile):
        build_dir = self._get_build_dir()
        book_config_dir = os.path.join(build_dir, "books", book, "config")

        if not os.path.exists(book_config_dir):
            sys.exit(f"Error: Book '{book}' does not exist. Add it first with 'add-book'.")

        profile_path = os.path.join(book_config_dir, profile)
        os.makedirs(profile_path, exist_ok=True)

        files = [
            ("parser.toml.skel", "parser.toml"),
            ("scripter.toml.skel", "scripter.toml"),
            ("executer.toml.skel", "executer.toml"),
            ("template.script", "template.script"),
        ]
        for src, dest in files:
            shutil.copy(os.path.join(self.skel_dir, src), os.path.join(profile_path, dest))
        print(f"Profile '{profile}' created under book '{book}'. Configs initialized in {profile_path}")

    def list_profiles(self, book):
        build_dir = self._get_build_dir()
        book_config_dir = os.path.join(build_dir, "books", book, "config")

        if not os.path.exists(book_config_dir):
            sys.exit(f"Error: Book '{book}' does not exist.")

        profiles = [
            d for d in os.listdir(book_config_dir)
            if os.path.isdir(os.path.join(book_config_dir, d)) and d != "book.toml"
        ]
        if profiles:
            print(f"Profiles for book '{book}':")
            for p in profiles:
                print(f"  - {p}")
        else:
            print(f"No profiles found for book '{book}'.")

    # -------------------------------
    # Workflow stubs
    # -------------------------------
    def parse_book(self, book, profile):
        print(f"[STUB] parse called for book '{book}' profile '{profile}' (XML -> JSON not yet implemented)")

    def script_book(self, book, profile):
        print(f"[STUB] script called for book '{book}' profile '{profile}' (JSON -> shell scripts not yet implemented)")

    def execute_book(self, book, profile):
        print(f"[STUB] execute called for book '{book}' profile '{profile}' (scripts -> packages not yet implemented)")


def main():
    parser = argparse.ArgumentParser(prog="skw-build", description="ScratchKit LFS Builder Toolset")
    sub = parser.add_subparsers(dest="command")

    # Core
    sub.add_parser("configure", help="Initialize builder.toml")

    # Books
    add_book = sub.add_parser("add-book", help="Add a new book")
    add_book.add_argument("--name", required=True, help="Name of the book")

    list_books = sub.add_parser("list-books", help="List all books")

    install_book = sub.add_parser("install-book", help="Install book (git clone, checkout, make)")
    install_book.add_argument("--book", required=True, help="Book name")

    # Profiles
    add_profile = sub.add_parser("add-profile", help="Add a new profile")
    add_profile.add_argument("--book", required=True, help="Book name")
    add_profile.add_argument("--name", required=True, help="Profile name")

    list_profiles = sub.add_parser("list-profiles", help="List profiles for a book")
    list_profiles.add_argument("--book", required=True, help="Book name")

    # Workflow
    parse_cmd = sub.add_parser("parse", help="Parse book XML -> JSON")
    parse_cmd.add_argument("--book", required=True, help="Book name")
    parse_cmd.add_argument("--profile", required=True, help="Profile name")

    script_cmd = sub.add_parser("script", help="Generate build scripts from JSON")
    script_cmd.add_argument("--book", required=True, help="Book name")
    script_cmd.add_argument("--profile", required=True, help="Profile name")

    execute_cmd = sub.add_parser("execute", help="Execute build scripts -> packages")
    execute_cmd.add_argument("--book", required=True, help="Book name")
    execute_cmd.add_argument("--profile", required=True, help="Profile name")

    args = parser.parse_args()
    builder = Builder()

    if args.command == "configure":
        builder.configure()
    elif args.command == "add-book":
        builder.add_book(args.name)
    elif args.command == "list-books":
        builder.list_books()
    elif args.command == "install-book":
        builder.install_book(args.book)
    elif args.command == "add-profile":
        builder.add_profile(args.book, args.name)
    elif args.command == "list-profiles":
        builder.list_profiles(args.book)
    elif args.command == "parse":
        builder.parse_book(args.book, args.profile)
    elif args.command == "script":
        builder.script_book(args.book, args.profile)
    elif args.command == "execute":
        builder.execute_book(args.book, args.profile)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

