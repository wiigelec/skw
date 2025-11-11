"""
git_builder.py
---------------
Implements the `GitBuilder` class and a command-line wrapper to automate
Git-based source builds, as defined in the 'Git Source Builder Module Specification'.

Usage:
    python -m git_builder build --config path/to/git_builder.toml
"""

import os
import shutil
import subprocess
import sys
import argparse

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import toml as tomllib  # Fallback for earlier versions


# ------------------------------
# Custom Exceptions
# ------------------------------

class GitBuilderError(Exception):
    """Base class for all GitBuilder exceptions."""


class ConfigError(GitBuilderError):
    """Raised when configuration is missing or invalid."""


class GitError(GitBuilderError):
    """Raised for Git-related errors."""


class BuildError(GitBuilderError):
    """Raised when the build command fails."""


# ------------------------------
# GitBuilder Class
# ------------------------------

class GitBuilder:
    """Automated Git-based source build orchestrator."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.repo_url = None
        self.version = None
        self.target_dir = None
        self.build_command = None
        self.output_file = None
        print(f"[INIT] GitBuilder initialized with config: {self.config_path}")
        self._load_config()

    def _load_config(self):
        """Load and validate configuration from a TOML file."""
        if not os.path.isfile(self.config_path):
            raise ConfigError(f"Configuration file not found: {self.config_path}")
	
        try:
            if hasattr(tomllib, "load") and "tomllib" in sys.modules:
                # Python 3.11+ — tomllib expects binary mode
                with open(self.config_path, "rb") as f:
                    data = tomllib.load(f)
            else:
                # Older Python — toml expects text mode
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = tomllib.load(f)
        except Exception as e:
            raise ConfigError(f"Failed to read TOML: {e}")
            
        cfg = data.get("config")
        if not cfg or not isinstance(cfg, dict):
            raise ConfigError("Missing or invalid [config] table in TOML file.")

        required = ["repo_url", "version", "target_dir", "build_command", "output_file"]
        missing = [k for k in required if k not in cfg]
        if missing:
            raise ConfigError(f"Missing required keys: {', '.join(missing)}")

        self.repo_url = cfg["repo_url"]
        self.version = cfg["version"]
        self.target_dir = cfg["target_dir"]
        self.build_command = cfg["build_command"]
        self.output_file = cfg["output_file"]

        print(f"[CONFIG] Loaded configuration for repo: {self.repo_url}")

    def _execute_command(self, command, work_dir=None, use_shell=True):
        """Execute a shell command and capture output."""
        print(f"[CMD] {command}")
        result = subprocess.run(
            command,
            shell=use_shell,
            cwd=work_dir,
            text=True,
            capture_output=True
        )
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.stderr.strip():
            print(result.stderr.strip())

        if result.returncode != 0:
            raise GitBuilderError(f"Command failed ({result.returncode}): {command}")

        return result

    def _clone_repo(self):
        """Clone or update the repository."""
        print(f"[GIT] Preparing {self.target_dir}")
        os.makedirs(self.target_dir, exist_ok=True)

        if os.path.exists(os.path.join(self.target_dir, ".git")):
            print(f"[GIT] Repo exists — pulling updates.")
            self._execute_command("git pull", work_dir=self.target_dir)
        else:
            print(f"[GIT] Cloning {self.repo_url} into {self.target_dir}")
            self._execute_command(f"git clone {self.repo_url} {self.target_dir}")

    def _checkout_version(self):
        """Checkout the desired version (tag/branch/commit)."""
        print(f"[GIT] Checking out version: {self.version}")
        self._execute_command("git fetch --all", work_dir=self.target_dir)
        self._execute_command(f"git checkout {self.version}", work_dir=self.target_dir)

    def _run_build(self):
        """Run the user-defined build command."""
        print(f"[BUILD] Running build command...")
        self._execute_command(self.build_command, work_dir=self.target_dir)
        print(f"[BUILD] Expected output: {self.output_file}")

    def build(self):
        """Full orchestration: clone ? checkout ? build."""
        try:
            print("[RUN] Build process started.")
            self._clone_repo()
            self._checkout_version()
            self._run_build()
            print("[SUCCESS] Build finished successfully.")
            return True
        except GitBuilderError as e:
            print(f"[ERROR] {e}")
            return False


# ------------------------------
# CLI Wrapper
# ------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="git-builder",
        description="Automated Git source build tool."
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # `build` command
    build_parser = subparsers.add_parser("build", help="Run the build process")
    build_parser.add_argument(
        "--config", "-c",
        required=True,
        help="Path to TOML configuration file"
    )

    args = parser.parse_args()

    if args.command == "build":
        builder = GitBuilder(args.config)
        success = builder.build()
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
