#!/usr/bin/env python3
"""
skw_executer.py
Execution engine for ScratchKit (SKW) pipeline.
"""

import os
import sys
import json
import tarfile
import shutil
import subprocess
import requests
import tomllib
import socket
import platform
import hashlib
from pathlib import Path
from datetime import datetime


class SKWExecuter:
    def __init__(self, build_dir, profiles_dir, book, profile, auto_confirm=False):
        self.build_dir = Path(build_dir)
        self.profiles_dir = Path(profiles_dir)
        self.book = book
        self.profile = profile
        self.exec_dir = self.build_dir / "executer" / book / profile
        self.logs_dir = self.exec_dir / "logs"
        self.downloads_dir = self.exec_dir / "downloads"
        self.auto_confirm = auto_confirm

        # Load executer.toml
        cfg_path = self.profiles_dir / book / profile / "executer.toml"
        if not cfg_path.exists():
            sys.exit(f"ERROR: missing {cfg_path}")
        with open(cfg_path, "rb") as f:
            self.cfg = tomllib.load(f)

        # Load parser output
        parser_out = self.build_dir / "parser" / book / profile / "parser_output.json"
        if not parser_out.exists():
            sys.exit(f"ERROR: missing {parser_out}")
        with open(parser_out, "r", encoding="utf-8") as f:
            self.entries = json.load(f)

        # Scripts dir
        self.scripts_dir = self.build_dir / "scripter" / book / profile / "scripts"
        if not self.scripts_dir.exists():
            sys.exit(f"ERROR: missing {self.scripts_dir}")

        # Ensure dirs
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

        # Config
        self.upload_repo = self.cfg["main"].get("upload_repo", "")
        self.download_repos = self.cfg["main"].get("download_repos", [])
        if not self.download_repos and "download_repo" in self.cfg["main"]:
            self.download_repos = [self.cfg["main"]["download_repo"]]

        self.chroot_dir = Path(self.cfg["main"].get("chroot_dir", self.exec_dir / "chroot"))
        self.default_extract_dir = self.cfg["main"].get("default_extract_dir", "/")
        self.require_confirm_root = self.cfg["main"].get("require_confirm_root", True)

    def run_all(self):
        scripts = sorted(self.scripts_dir.glob("*.sh"))
        for script in scripts:
            entry = self._find_metadata(script.name)
            pkg_file = self._pkg_filename(entry)

            # Step A: cache check
            if self._package_exists(pkg_file):
                self._install_package(pkg_file, entry)
                self._log_skip(script, pkg_file)
                continue

            # Step B: run script
            exec_mode = self._exec_mode(entry)
            make_package = self._should_package(entry)
            destdir = None
            if make_package:
                destdir = self._make_destdir(exec_mode, entry)
                rc = self._run_script(script, entry, exec_mode, destdir)
            else:
                rc = self._run_script(script, entry, exec_mode, None)

            if rc != 0:
                sys.exit(f"ERROR: script {script} failed with code {rc}")

            # Step C/D/E: package, install, upload
            if make_package:
                archive = self._create_archive(destdir, pkg_file, entry, exec_mode)
                self._install_package(archive, entry)
                self._upload_package(archive)

    # ---------------------------
    # Core helpers
    # ---------------------------

    def _find_metadata(self, script_name):
        for e in self.entries:
            if e.get("script_name") == script_name:
                return e
        sys.exit(f"ERROR: no metadata for {script_name}")

    def _pkg_filename(self, entry):
        tmpl = self.cfg["main"]["package_name_template"]
        return tmpl.format(**{
            "book": self.book,
            "profile": self.profile,
            "chapter_id": entry.get("chapter_id", ""),
            "section_id": entry.get("section_id", ""),
            "package_name": entry.get("package_name", ""),
            "package_version": entry.get("package_version", "")
        }) + "." + self.cfg["main"].get("package_format", "tar.xz")

    def _exec_mode(self, entry):
        c = self.cfg.get("chroot", {})
        if entry.get("package_name") in c.get("packages", []):
            return "chroot"
        if entry.get("section_id") in c.get("sections", []):
            return "chroot"
        if entry.get("chapter_id") in c.get("chapters", []):
            return "chroot"
        return "host"

    def _should_package(self, entry):
        pkg = entry.get("package_name", "")
        ver = entry.get("package_version", "")
        sec = entry.get("section_id", "")
        chap = entry.get("chapter_id", "")

        inc = self.cfg.get("package", {})
        exc = self.cfg.get("packages", {}).get("exclude", {})

        include = (
            pkg in inc.get("packages", [])
            or f"{pkg}-{ver}" in inc.get("packages", [])
            or sec in inc.get("sections", [])
            or chap in inc.get("chapters", [])
        )

        exclude = (
            pkg in exc.get("packages", [])
            or f"{pkg}-{ver}" in exc.get("packages", [])
            or sec in exc.get("sections", [])
            or chap in exc.get("chapters", [])
        )

        return include and not exclude

    def _make_destdir(self, mode, entry):
        pkg = entry.get("package_name")
        if mode == "host":
            destdir = self.exec_dir / "destdir" / pkg
        else:
            destdir = self.chroot_dir / "destdir" / pkg
        destdir.mkdir(parents=True, exist_ok=True)
        return str(destdir)

    def _run_script(self, script, entry, mode, destdir=None):
        log_path = self.logs_dir / (script.name + ".log")
        with open(log_path, "w", encoding="utf-8") as logf:
            if mode == "chroot":
                cmd = ["chroot", str(self.chroot_dir), "/bin/bash", f"/scripts/{script.name}"]
                if destdir:
                    cmd.append(destdir)
            else:
                cmd = ["/bin/bash", str(script)]
                if destdir:
                    cmd.append(destdir)

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                sys.stdout.write(line)
                logf.write(line)
            proc.wait()
            return proc.returncode

    def _create_archive(self, destdir, pkg_file, entry, exec_mode):
        out_path = self.exec_dir / "packages" / pkg_file
        out_path.parent.mkdir(parents=True, exist_ok=True)

        fmt = self.cfg["main"].get("package_format", "tar.xz")
        mode = {"tar": "w", "tar.gz": "w:gz", "tar.xz": "w:xz"}[fmt]

        with tarfile.open(out_path, mode) as tar:
            tar.add(destdir, arcname="/")

        sha256 = self._sha256_file(out_path)

        metadata = {
            "package_name": entry.get("package_name"),
            "package_version": entry.get("package_version"),
            "book": self.book,
            "profile": self.profile,
            "chapter_id": entry.get("chapter_id"),
            "section_id": entry.get("section_id"),
            "exec_mode": exec_mode,
            "build_date": datetime.utcnow().isoformat() + "Z",
            "builder_host": platform.machine(),
            "builder_os": platform.platform(),
            "builder_user": os.environ.get("USER", "unknown"),
            "hostname": socket.gethostname(),
            "archive": str(out_path),
            "size": out_path.stat().st_size,
            "sha256": sha256,
            "files": self._list_files(destdir)
        }
        meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return out_path

    def _sha256_file(self, path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _list_files(self, root):
        files = []
        for base, _, names in os.walk(root):
            for n in names:
                files.append(os.path.relpath(os.path.join(base, n), root))
        return files

    def _package_exists(self, pkg_file):
        meta_name = pkg_file + ".meta.json"
        for repo in self.download_repos:
            if repo.startswith("http"):
                meta_url = f"{repo.rstrip('/')}/{meta_name}"
                try:
                    r = requests.head(meta_url, timeout=5)
                    if r.status_code == 200:
                        self._found_repo = repo
                        self._found_meta = meta_name
                        return True
                except requests.RequestException:
                    continue
            else:
                meta_path = Path(repo) / meta_name
                if meta_path.exists():
                    self._found_repo = repo
                    self._found_meta = meta_path
                    return True
        return False

    def _install_package(self, pkg_file, entry):
        repo = getattr(self, "_found_repo", None)
        meta_ref = getattr(self, "_found_meta", None)
        if not repo or not meta_ref:
            sys.exit("ERROR: _install_package called without resolved repo/metadata")

        meta_name = pkg_file + ".meta.json"

        if repo.startswith("http"):
            url = f"{repo.rstrip('/')}/{pkg_file}"
            local_tmp = self.downloads_dir / pkg_file
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(local_tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            pkg_path = local_tmp

            meta_url = f"{repo.rstrip('/')}/{meta_name}"
            local_meta = self.downloads_dir / meta_name
            r = requests.get(meta_url)
            r.raise_for_status()
            with open(local_meta, "wb") as f:
                f.write(r.content)
            meta_path = local_meta

        else:
            pkg_path = Path(repo) / pkg_file
            meta_path = Path(repo) / meta_name

        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        expected_sha = metadata.get("sha256")
        actual_sha = self._sha256_file(pkg_path)
        if expected_sha != actual_sha:
            sys.exit(f"ERROR: checksum mismatch for {pkg_file}\nExpected: {expected_sha}\nActual:   {actual_sha}")

        exec_mode = self._exec_mode(entry)
        if exec_mode == "chroot":
            target = self.chroot_dir
        else:
            pkg = entry.get("package_name", "")
            sec = entry.get("section_id", "")
            chap = entry.get("chapter_id", "")
            targets = self.cfg.get("extract.targets", {})
            target = (
                targets.get("packages", {}).get(pkg) or
                targets.get("sections", {}).get(sec) or
                targets.get("chapters", {}).get(chap) or
                self.default_extract_dir
            )

            if str(target) == "/" and self.require_confirm_root and not self.auto_confirm:
                ans = input(f"WARNING: installing {pkg_file} into /. Continue? [y/N] ")
                if ans.lower() not in ["y", "yes"]:
                    sys.exit("Aborted")

        with tarfile.open(pkg_path, "r:*") as tar:
            tar.extractall(path=target)

    def _upload_package(self, archive):
        if self.upload_repo.startswith("http"):
            sys.exit("ERROR: upload_repo cannot be http (only local path or scp)")
        if ":" in self.upload_repo:  # scp target
            subprocess.check_call(["scp", str(archive), self.upload_repo])
            subprocess.check_call(["scp", str(archive) + ".meta.json", self.upload_repo])
        else:
            shutil.copy2(archive, Path(self.upload_repo))
            shutil.copy2(str(archive) + ".meta.json", Path(self.upload_repo))

    def _log_skip(self, script, pkg_file):
        log_path = self.logs_dir / (script.name + ".log")
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(f"\nSKIPPED: using cached {pkg_file} from {self._found_repo}\n")
