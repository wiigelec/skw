#!/usr/bin/env python3
import os
import sys
import glob
import tomllib
import argparse
import shutil
import subprocess

from skw_parser import SKWParser
from skw_scripter import SKWScripter
from skw_executer import SKWExecuter

class Builder:
    def __init__(self, config_path="builder.toml", skel_dir="src/config/skel"):
        if not os.path.exists(config_path):
            sys.exit("Error: builder.toml not found. Run skw-build --configure first.")

        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)

        self.build_dir = os.path.abspath(cfg["paths"]["build_dir"])
        self.package_dir = os.path.abspath(cfg["paths"]["package_dir"])
        self.profiles_dir = os.path.abspath(cfg["paths"]["profiles_dir"])
        self.skel_dir = os.path.abspath(skel_dir)

        os.makedirs(self.build_dir, exist_ok=True)
        os.makedirs(self.package_dir, exist_ok=True)

    # -------------------
    # Book + Profile
    # -------------------
    def add_book(self, name):
        book_path = os.path.join(self.profiles_dir, name)
        if os.path.exists(book_path):
            sys.exit(f"Book {name} already exists in profiles/")
        os.makedirs(book_path, exist_ok=True)

        src = os.path.join(self.skel_dir, "book.toml.skel")
        dst = os.path.join(book_path, "book.toml")
        shutil.copyfile(src, dst)

        print(f"Book {name} created at {book_path}")
        print(f"Edit {dst} before running install-book")

    def add_profile(self, book, profile):
        book_path = os.path.join(self.profiles_dir, book)
        if not os.path.exists(book_path):
            sys.exit(f"Book {book} does not exist. Run add-book first.")

        profile_path = os.path.join(book_path, profile)
        if os.path.exists(profile_path):
            sys.exit(f"Profile {profile} already exists under {book}")

        os.makedirs(profile_path, exist_ok=True)

        src_dir = self.skel_dir
        skeletons = ["parser.toml.skel", "scripter.toml.skel", "executer.toml.skel"]
        scripts = glob.glob(os.path.join(src_dir, "*.script"))

        # copy skeletons
        for fname in skeletons:
            src = os.path.join(src_dir, fname)
            dst = os.path.join(profile_path, fname.replace(".skel", ""))
            shutil.copyfile(src, dst)

        # copy scripts
        for src in scripts:
            fname = os.path.basename(src)
            dst = os.path.join(profile_path, fname.replace(".skel", ""))
            shutil.copyfile(src, dst)

        print(f"Profile {profile} created at {profile_path}")
        print("Edit configs before parsing.")

    def list_books(self):
        if not os.path.exists(self.profiles_dir):
            sys.exit("Profiles directory not found.")
        books = [d for d in os.listdir(self.profiles_dir)
                 if os.path.isdir(os.path.join(self.profiles_dir, d))]
        print("Available books:", books)

    def list_profiles(self, book):
        path = os.path.join(self.profiles_dir, book)
        if not os.path.isdir(path):
            sys.exit(f"Book not found: {book}")
        profiles = [d for d in os.listdir(path)
                    if os.path.isdir(os.path.join(path, d))]
        print(f"Profiles for {book}:", profiles)

    # -------------------
    # Book installation
    # -------------------
    def install_book(self, book):
        book_path = os.path.join(self.profiles_dir, book, "book.toml")
        if not os.path.exists(book_path):
            sys.exit(f"book.toml not found for {book}. Did you run add-book?")

        with open(book_path, "rb") as f:
            book_cfg = tomllib.load(f)["main"]

        repo_path = book_cfg["repo_path"]
        version = book_cfg["version"]
        rev = book_cfg["rev"]
        make_command = book_cfg["make_command"]
        output_file = book_cfg["output_file"]

        repo_dir = os.path.join(self.build_dir, "books", book, "src")
        os.makedirs(repo_dir, exist_ok=True)

        if not os.listdir(repo_dir):
            print(f"Cloning {repo_path} into {repo_dir}")
            subprocess.run(f"git clone {repo_path} {repo_dir}", shell=True, check=True)
        else:
            print("Book repo already exists, pulling latest changes...")
            subprocess.run("git pull", shell=True, check=True, cwd=repo_dir)

        subprocess.run(f"git checkout {version}", shell=True, check=True, cwd=repo_dir)

        # Expand vars in make command
        env = os.environ.copy()
        env["book_dir"] = os.path.join(self.build_dir, "books", book)
        env["rev"] = rev
        expanded_command = make_command.replace("${book_dir}", env["book_dir"]).replace("${rev}", rev)

        print(f"Running make command: {expanded_command}")
        subprocess.run(expanded_command, shell=True, check=True, cwd=repo_dir, env=env)

        xml_dst = os.path.join(self.build_dir, "books", book, output_file)

        if os.path.exists(xml_dst):
            print(f"Installed book {book}. XML available at {xml_dst}")
        else:
            print(f"XML book generation failed.")

    # -------------------
    # Parser / Scripter / Executer
    # -------------------
    def parse_book(self, book, profile):
        parser = SKWParser(self.build_dir, self.profiles_dir, book, profile)
        parser.run()

    def script_book(self, book, profile):
        scripter = SKWScripter(self.build_dir, self.profiles_dir, book, profile)
        scripter.run()

    def execute_book(self, book, profile, auto_confirm=False):
        executer = SKWExecuter(self.build_dir, self.profiles_dir, book, profile, auto_confirm=auto_confirm)
        executer.run_all()


# -------------------
# CLI
# -------------------
def main():
    parser = argparse.ArgumentParser(description="ScratchKit Builder CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list-books")
    p = sub.add_parser("list-profiles")
    p.add_argument("--book", required=True)

    p = sub.add_parser("add-book")
    p.add_argument("--name", required=True)

    p = sub.add_parser("add-profile")
    p.add_argument("--book", required=True)
    p.add_argument("--name", required=True)

    p = sub.add_parser("install-book")
    p.add_argument("--book", required=True)

    p = sub.add_parser("parse")
    p.add_argument("--book", required=True)
    p.add_argument("--profile", required=True)

    p = sub.add_parser("script")
    p.add_argument("--book", required=True)
    p.add_argument("--profile", required=True)

    p = sub.add_parser("execute")
    p.add_argument("--book", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--yes", action="store_true", help="auto confirm dangerous actions")

    args = parser.parse_args()
    builder = Builder()

    if args.command == "list-books":
        builder.list_books()
    elif args.command == "list-profiles":
        builder.list_profiles(args.book)
    elif args.command == "add-book":
        builder.add_book(args.name)
    elif args.command == "add-profile":
        builder.add_profile(args.book, args.name)
    elif args.command == "install-book":
        builder.install_book(args.book)
    elif args.command == "parse":
        builder.parse_book(args.book, args.profile)
    elif args.command == "script":
        builder.script_book(args.book, args.profile)
    elif args.command == "execute":
        builder.execute_book(args.book, args.profile, auto_confirm=args.yes)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

