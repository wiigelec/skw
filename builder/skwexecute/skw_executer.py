#!/usr/bin/env python3
# ================================================================
#
# skw_executer.py
#
# ================================================================

import os
import sys
import json
import tarfile
import shutil
import subprocess
import requests
import toml
import socket
import platform
import hashlib
import re
import yaml
from pathlib import Path
from datetime import datetime

#------------------------------------------------------------------#
class SKWExecuter:
    def __init__(self, build_dir, profiles_dir, book, profile, auto_confirm=False):
        self.build_dir = Path(build_dir)
        self.profiles_dir = Path(profiles_dir)
        self.book = book
        self.profile = profile
        self.exec_dir = self.build_dir / book / profile / "executer" 
        self.logs_dir = self.exec_dir / "logs"
        self.downloads_dir = self.exec_dir / "downloads"
        self.auto_confirm = auto_confirm

        # Load executer.toml
        cfg_path = self.profiles_dir / book / profile / "executer.toml"
        if not cfg_path.exists():
            sys.exit(f"ERROR: missing {cfg_path}")
        with open(cfg_path, "r", encoding="utf-8") as f:
            self.cfg = toml.load(f)

        # 1. BUILD METADATA REGISTRY
        # We map (slugged_chapter, slugged_section) -> yaml_entry
        self.metadata_registry = {}
        parser_dir = self.build_dir / book / "parser"  / "build_metadata"
        if not parser_dir.exists():
            sys.exit(f"ERROR: missing {parser_dir}")

        for yfile in parser_dir.glob("*.yaml"):
            with open(yfile, "r", encoding="utf-8") as f:
                entry = yaml.safe_load(f) or {}
                # Normalize keys to match Scripter's slugging logic
                c_slug = self._slug(entry.get("chapter_id", ""))
                s_slug = self._slug(entry.get("section_id", ""))

                # Store by the IDs used in the filename
                self.metadata_registry[(c_slug, s_slug)] = entry

        # 2. IDENTIFY SCRIPTS
        self.scripts_dir = self.build_dir / book / profile / "scripter" / "scripts"
        if not self.scripts_dir.exists():
            sys.exit(f"ERROR: missing {self.scripts_dir}")

        # Ensure dirs
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

        # Path substitution logic
        builder_cfg = {}
        if Path("builder.toml").exists():
            with open("builder.toml", "r", encoding="utf-8") as bf:
                builder_cfg = toml.load(bf)

        vars_map = {
            "build_dir": str(self.build_dir),
            "profiles_dir": str(self.profiles_dir),
            "package_dir": str(builder_cfg.get("paths", {}).get("package_dir", "")),
            "book": self.book,
            "profile": self.profile,
        }

        # RESOLVE package_dir FIRST
        raw_pkg_dir = self.cfg["main"].get("package_dir", str(self.exec_dir / "packages"))
        expanded_pkg_dir = self._expand_vars(raw_pkg_dir, vars_map)
        # Use .resolve() to ensure it is an absolute path
        self.package_dir = Path(expanded_pkg_dir).resolve()
        self.package_dir.mkdir(parents=True, exist_ok=True)

        # UPDATE vars_map with the absolute path for subsequent expansions
        vars_map["package_dir"] = str(self.package_dir)

        # NOW expand download_repos using the updated vars_map
        self.download_repos = [
            self._expand_vars(r, vars_map) for r in self.cfg["main"].get("download_repos", [])
        ]

        self.upload_repo = self._expand_vars(self.cfg["main"].get("upload_repo", ""), vars_map)

        self.package_dir = Path(self._expand_vars(self.cfg["main"].get("package_dir", str(self.exec_dir / "packages")), vars_map))
        self.package_dir.mkdir(parents=True, exist_ok=True)
        self.download_repos = [self._expand_vars(r, vars_map) for r in self.cfg["main"].get("download_repos", [])]
        self.chroot_dir = Path(self.cfg["main"].get("chroot_dir", self.exec_dir / "chroot"))
        self.default_extract_dir = self.cfg["main"].get("default_extract_dir", "/")
        self.require_confirm_root = self.cfg["main"].get("require_confirm_root", True)

    #------------------------------------------------------------------#
    def _slug(self, s: str) -> str:
        """Mirror the Scripter's slugging to ensure ID keys match filenames."""
        s = str(s).strip().lower()
        s = s.replace("/", "_").replace("\\", "_")
        s = re.sub(r"\s+", "-", s)
        s = re.sub(r"[^a-z0-9._+-]+", "-", s)
        s = re.sub(r"-{2,}", "-", s).strip("-")
        return s or "unnamed"

    #------------------------------------------------------------------#
    def parse_script_name(self, fname):
        """Extract IDs from {order}_{chapter_id}_{section_id}.sh"""
        base = Path(fname).stem
        parts = base.split("_")
        if len(parts) < 3:
            return None, None, None
        order = parts[0]
        chap_id = parts[1]
        sec_id = "_".join(parts[2:])
        return order, chap_id, sec_id

    #------------------------------------------------------------------#
    def _find_metadata(self, script_name):
        """Use the Registry to find metadata by the IDs in the filename."""
        _, chap_slug, sec_slug = self.parse_script_name(script_name)
        entry = self.metadata_registry.get((chap_slug, sec_slug))

        if not entry:
            sys.exit(f"ERROR: No YAML metadata found for key: ({chap_slug}, {sec_slug}) from {script_name}")

        # Normalize package keys for the rest of the executer logic
        entry["package_name"] = entry.get("name", "")
        entry["package_version"] = entry.get("version", "")
        return entry

    #------------------------------------------------------------------#
    def run_all(self):
        scripts = sorted(self.scripts_dir.glob("*.sh"))

        for script in scripts:
            entry = self._find_metadata(script.name)
            pkg_file = self._pkg_filename(entry)

            # 1. CHECK CACHE
            pkg_data = self._package_exists(pkg_file)
            
            #print(f"[DEBUG] Looking for cached package: {pkg_data}")

            if pkg_data:
                # INSTALL THE CACHE and skip building
                print(f"[CACHE] Found {pkg_file} in {pkg_data['repo']}. Installing...")
                self._install_package(pkg_file, entry, pkg_data)
                self._log_skip(script, pkg_file, pkg_data['repo'])
                # This ensures we skip the build logic below
                continue

            # 2. BUILD (Only reached if no cache found)
            exec_mode = self._exec_mode(entry)
            make_package = self._should_package(entry)
            destdir = self._make_destdir(exec_mode, entry) if make_package else None

            rc = self._run_script(script, entry, exec_mode, destdir)
            if rc != 0:
                sys.exit(f"ERROR: script {script} failed with code {rc}")

            # 3. PACKAGE & CLEANUP
            if make_package:
                archive = self._create_archive(destdir, pkg_file, entry, exec_mode)
                self._install_local_package(archive, entry)
                self._upload_package(archive)

                # CLEANUP: Remove staging dir so it doesn't clutter CWD
                if destdir and Path(destdir).exists():
                    shutil.rmtree(destdir, ignore_errors=True)

    #------------------------------------------------------------------#
    def _pkg_filename(self, entry):
        tmpl = self.cfg["main"]["package_name_template"]

        pkg = entry.get("package_name")
        if not pkg:
            pkg = entry.get("section_id") or "noname"

        ver = entry.get("package_version") or "noversion"

        values = {
            "book": self.book,
            "profile": self.profile,
            "chapter_id": entry.get("chapter_id", ""),
            "section_id": entry.get("section_id", ""),
            "package_name": pkg,
            "package_version": ver,
        }

        tmpl = re.sub(r"\$\{([^}]+)\}", r"{\1}", tmpl)
        return tmpl.format(**values) + "." + self.cfg["main"].get("package_format", "tar.xz")

    #------------------------------------------------------------------#
    def _exec_mode(self, entry):
        # Host rules take precedence
        h = self.cfg.get("host", {})
        if entry.get("package_name") in h.get("packages", []):
            return "host"
        if entry.get("section_id") in h.get("sections", []):
            return "host"
        if entry.get("chapter_id") in h.get("chapters", []):
            return "host"

        # Then chroot rules
        c = self.cfg.get("chroot", {})
        if entry.get("package_name") in c.get("packages", []):
            return "chroot"
        if entry.get("section_id") in c.get("sections", []):
            return "chroot"
        if entry.get("chapter_id") in c.get("chapters", []):
            return "chroot"

        # Default fallback
        return "host"

    #------------------------------------------------------------------#
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

    #------------------------------------------------------------------#
    def _make_destdir(self, mode, entry):
        """Creates a staging directory isolated from the working directory."""
        pkg = entry.get("package_name") or entry.get("section_id")

        # Use the exec_dir (build_dir/book/profile/executer) to house destdirs
        # This keeps the current working directory clean.
        base_dest = self.exec_dir / "destdir" / pkg

        if mode == "chroot":
            # If in chroot, the physical path is inside the chroot mount point
            destdir = self.chroot_dir / "destdir" / pkg
        else:
            destdir = base_dest

        if destdir.exists():
            shutil.rmtree(destdir)
        destdir.mkdir(parents=True, exist_ok=True)

        return str(destdir)

    #------------------------------------------------------------------#
    def _run_script(self, script, entry, mode, destdir=None):
        log_path = self.logs_dir / (script.name + ".log")
        with open(log_path, "w", encoding="utf-8") as logf:
            mounts = []
            if mode == "chroot":
                print(f"[INFO] Running in chroot mode for script {script}")
                scripts_target = self.chroot_dir / "scripts"
                dev_target = self.chroot_dir / "dev"
                proc_target = self.chroot_dir / "proc"
                sys_target = self.chroot_dir / "sys"
    
                scripts_target.mkdir(parents=True, exist_ok=True)
                dev_target.mkdir(parents=True, exist_ok=True)
                proc_target.mkdir(parents=True, exist_ok=True)
                sys_target.mkdir(parents=True, exist_ok=True)
    
                bind_mounts = [
                    (str(self.scripts_dir), str(scripts_target)),
                    ("/dev", str(dev_target)),
                    ("/proc", str(proc_target)),
                    ("/sys", str(sys_target)),
                ]
    
                for src, dst in bind_mounts:
                    try:
                        subprocess.run(["mount", "--bind", src, dst], check=True)
                        mounts.append(dst)
                    except subprocess.CalledProcessError as e:
                        sys.exit(f"ERROR: failed to bind-mount {src} -> {dst}: {e}")
    
                # Important: pass only the *chroot-internal* destdir
                cmd = ["chroot", str(self.chroot_dir), "/bin/bash", f"/scripts/{script.name}"]
                if destdir:
                    internal_destdir = "/" + str(Path(destdir).relative_to(self.chroot_dir))
                    cmd.append(internal_destdir)
            else:
                print(f"[INFO] Running in host mode for script {script}")
                cmd = ["/bin/bash", str(script)]
                if destdir:
                    cmd.append(destdir)
    
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                for line in proc.stdout:
                    sys.stdout.write(line)
                    logf.write(line)
                proc.wait()
            finally:
                if mode == "chroot":
                    for m in reversed(mounts):
                        subprocess.run(["umount", "-lf", m], check=False)
    
            return proc.returncode

    #------------------------------------------------------------------#
    def _create_archive(self, destdir, pkg_file, entry, exec_mode):
        """Creates the compressed archive in the designated package directory."""
        # Force the output path to be inside the configured package_dir
        out_path = (self.package_dir / pkg_file).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        fmt = self.cfg["main"].get("package_format", "tar.xz")
        mode = {"tar": "w", "tar.gz": "w:gz", "tar.xz": "w:xz"}[fmt]

        # Archive the staging directory
        with tarfile.open(out_path, mode) as tar:
            tar.add(destdir, arcname="/")

        sha256 = self._sha256_file(out_path)

        # Generate accompanying metadata for future cache checks
        metadata = {
            "package_name": entry.get("package_name"),
            "package_version": entry.get("package_version"),
            "book": self.book,
            "profile": self.profile,
            "chapter_id": entry.get("chapter_id"),
            "section_id": entry.get("section_id"),
            "exec_mode": exec_mode,
            "build_date": datetime.utcnow().isoformat() + "Z",
            "hostname": socket.gethostname(),
            "sha256": sha256,
            "files": self._list_files(destdir)
        }

        meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        print(f"[PKG] Created package {out_path.name} in {self.package_dir}")
        return out_path

    #------------------------------------------------------------------#
    def _sha256_file(self, path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    #------------------------------------------------------------------#
    def _list_files(self, root):
        files = []
        for base, _, names in os.walk(root):
            for n in names:
                files.append(os.path.relpath(os.path.join(base, n), root))
        return files

    #------------------------------------------------------------------#
    def _package_exists(self, pkg_file):
        meta_name = pkg_file + ".meta.json"

        #print(f"[DEBUG] Checking if package exists: {meta_name}")

        for repo in self.download_repos:
            #print(f"[DEBUG] Checking repo: {repo}")
            if not repo:
                continue

            if repo.startswith("http"):
                meta_url = f"{repo.rstrip('/')}/{meta_name}"
                try:
                    r = requests.head(meta_url, timeout=5)
                    if r.status_code == 200:
                        return {"repo": str(repo), "meta": meta_name, "is_http": True}
                except requests.RequestException:
                    continue
            else:
                # FORCE absolute path resolution
                repo_path = Path(repo).resolve()
                meta_path = repo_path / meta_name
                pkg_path = repo_path / pkg_file

                if meta_path.exists() and pkg_path.exists():
                    return {
                        "repo": str(repo_path),
                        "meta": str(meta_path),
                        "is_http": False
                    }
        return None

    #------------------------------------------------------------------#
    def _install_package(self, pkg_file, entry, pkg_data):
        """
        Downloads (if remote) and extracts a cached package into the target system.

        Args:
            pkg_file (str): The filename of the package archive.
            entry (dict): The YAML metadata for the current package.
            pkg_data (dict): Dictionary containing 'repo', 'meta', and 'is_http' flags.
        """
        #print(f"[DEBUG] pkg_data received: {pkg_data}")
        repo = pkg_data.get("repo")
        meta_ref = pkg_data.get("meta")

        # Validation to prevent logic errors if called incorrectly
        if not repo or not meta_ref:
            sys.exit("ERROR: _install_package called without resolved repo/metadata")

        meta_name = pkg_file + ".meta.json"

        # Handle Remote HTTP Repositories
        if pkg_data.get("is_http"):
            url = f"{repo.rstrip('/')}/{pkg_file}"
            local_tmp = self.downloads_dir / pkg_file

            print(f"[HTTP] Downloading {pkg_file}...")
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
            # Handle Local Filesystem Repositories
            pkg_path = Path(repo) / pkg_file
            meta_path = Path(repo) / meta_name

        # Integrity Check: Compare SHA256 from metadata against actual file
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        expected_sha = metadata.get("sha256")
        actual_sha = self._sha256_file(pkg_path)

        if expected_sha != actual_sha:
            sys.exit(f"ERROR: checksum mismatch for {pkg_file}\n"
                     f"Expected: {expected_sha}\n"
                     f"Actual:   {actual_sha}")

        # Determine extraction target
        target = self._extract_package(pkg_path, entry)

        print(f"[PKG] Installed cached package {pkg_file} from {repo} into {target}")

    #------------------------------------------------------------------#
    def _install_local_package(self, archive, entry):
        meta_path = archive.with_suffix(archive.suffix + ".meta.json")
        if not meta_path.exists():
            sys.exit(f"ERROR: missing metadata {meta_path}")
    
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    
        expected_sha = metadata.get("sha256")
        actual_sha = self._sha256_file(archive)
        if expected_sha != actual_sha:
            sys.exit(f"ERROR: checksum mismatch for {archive}")
    
        target = self._extract_package(archive, entry)
        print(f"[PKG] Installed freshly built package {archive.name} into {target}")

    #------------------------------------------------------------------#
    def _extract_package(self, archive, entry):
        exec_mode = self._exec_mode(entry)
        if exec_mode == "chroot":
            target = self.chroot_dir
        else:
            pkg = entry.get("package_name", "")
            sec = entry.get("section_id", "")
            chap = entry.get("chapter_id", "")
            targets = self.cfg.get("extract.targets", {})
            target = (
                targets.get("packages", {}).get(pkg)
                or targets.get("sections", {}).get(sec)
                or targets.get("chapters", {}).get(chap)
                or self.default_extract_dir
            )
    
            if str(target) == "/" and self.require_confirm_root and not self.auto_confirm:
                ans = input(f"WARNING: installing {archive.name} into /. Continue? [y/N] ")
                if ans.lower() not in ["y", "yes"]:
                    sys.exit("Aborted")
    
        self._safe_extract(archive, target)
        return target

    #------------------------------------------------------------------#
    def _safe_extract(self, archive, target):
        """Safer tar extraction using system tar, but tolerant of symlinks and leading '/'."""
        target_path = Path(target).resolve()
    
        with tarfile.open(archive, "r:*") as tar:
            for member in tar.getmembers():
                # Strip leading '/' to handle absolute paths
                name = member.name.lstrip("/")
                member_path = (target_path / name).resolve()
    
                # Check symlinks separately
                if member.issym() or member.islnk():
                    # Allow symlinks; system tar will recreate them faithfully
                    continue
    
                if not str(member_path).startswith(str(target_path)):
                    sys.exit(f"SECURITY ERROR: illegal path in archive {archive} -> {member.name}")
    
        # If validation passes, extract with system tar
        # Run tar, but filter stderr so only "Removing leading '/'" messages are hidden
        cmd = [
            "tar",
            "--extract",
            "--file", str(archive),
            "--directory", str(target),
            "--preserve-permissions"
        ]
    
        try:
            # Use a shell pipeline to grep -v the noisy line
            subprocess.run(
                f"{' '.join(cmd)} 2> >(grep -v \"Removing leading \" >&2)",
                shell=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            sys.exit(f"ERROR: failed to extract {archive} to {target}: {e}")

    #------------------------------------------------------------------#
    def _upload_package(self, archive):
        if self.upload_repo.startswith("http"):
            sys.exit("ERROR: upload_repo cannot be http (only local path or scp)")
        if "${" in self.upload_repo:
            sys.exit(f"ERROR: unresolved variable in upload_repo: {self.upload_repo}")
        if ":" in self.upload_repo:  # scp target
            subprocess.check_call(["scp", str(archive), self.upload_repo])
            subprocess.check_call(["scp", str(archive) + ".meta.json", self.upload_repo])
        else:
            dest_dir = Path(self.upload_repo)
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archive, dest_dir)
            shutil.copy2(str(archive) + ".meta.json", dest_dir)

        print(f"[PKG] Uploaded package {archive.name} to {self.upload_repo}")
        
    #------------------------------------------------------------------#
    def _expand_vars(self, value, vars_map):
        """Expand ${var} placeholders and environment variables recursively."""
        if not isinstance(value, str):
            return value
    
        prev = None
        while prev != value:
            prev = value
            for k, v in vars_map.items():
                value = value.replace(f"${{{k}}}", v)
            value = os.path.expandvars(value)  # also expand $ENVVAR
    
        return value

    #------------------------------------------------------------------#
    def _log_skip(self, script, pkg_file, repo_name):
        """
        Logs that a script was skipped due to a cached package found in a repository.

        Args:
            script (Path): The Path object of the script being skipped.
            pkg_file (str): The name of the package file found.
            repo_name (str): The name or URL of the repository where the package was found.
        """
        log_path = self.logs_dir / (script.name + ".log")

        # Open in append mode to preserve any existing pre-check logs
        with open(log_path, "a", encoding="utf-8") as logf:
            # We use the explicitly passed repo_name instead of a class attribute
            logf.write(f"\nSKIPPED: using cached {pkg_file} from {repo_name}\n")

        print(f"[INFO] Skipped {script.name}: found cached {pkg_file} in {repo_name}")
