"""Files a recipe needs that only the user can download (PureDark's plugins on Nexus): Panel finds the archive the
user saved, checks it carries what the recipe names, keeps a copy and installs it like any other dependency."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

from . import pe

ARCHIVES = (".zip", ".7z", ".rar")
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_MEMBER = 256 * 1024 * 1024
MAX_SCANNED = 200
MAX_CANDIDATES = 5
# Nexus names downloads `<name>-<mod id>-<version with dashes>-<unix time>.<ext>`.
_NEXUS = re.compile(r"-\d+-(\d+(?:-\d+){1,3})-\d{1,12}\.[A-Za-z0-9]+$")
_DOTTED = re.compile(r"(?<![\d.])v?(\d+\.\d+(?:\.\d+){0,2})(?![\d.])")


class UserFileError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _filename_version(name: str) -> str | None:
    nexus = _NEXUS.search(name)
    if nexus:
        return nexus.group(1).replace("-", ".")
    dotted = _DOTTED.search(name)
    return dotted.group(1) if dotted else None


def _dll_version(path: Path) -> str | None:
    strings = pe.version_strings(str(path))
    for key in ("FileVersion", "ProductVersion"):
        found = _DOTTED.search(strings.get(key, "").replace(",", ".").replace(" ", ""))
        if found:
            return ".".join(found.group(1).split(".")[:3])
    return None


def _members(path: Path) -> list[str]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            return [info.filename for info in archive.infolist() if not info.is_dir()]
    result = subprocess.run(["bsdtar", "-tf", str(path.resolve())], capture_output=True, timeout=60, check=False)
    if result.returncode != 0:
        raise OSError("unreadable archive")
    return [line for line in result.stdout.decode("utf-8", "replace").splitlines() if line and not line.endswith("/")]


def _unsafe(member: str) -> bool:
    parts = PurePosixPath(member.replace("\\", "/")).parts
    # Member names reach bsdtar's command line: none may read as an option.
    return member.startswith(("/", "\\")) or ":" in member or ".." in parts or any(part.startswith("-") for part in parts)


def _locate(dependency, path: Path) -> dict[str, str]:
    """Wanted file name -> its member inside the archive (or the file itself for a loose DLL)."""
    wanted = {member.casefold(): member for member in dependency.files.values()}
    if path.suffix.lower() == ".dll":
        if set(wanted) != {path.name.casefold()}:
            raise UserFileError("missing_files")
        return {wanted[path.name.casefold()]: path.name}
    members = _members(path)
    if any(_unsafe(member) for member in members):
        raise UserFileError("unsafe_archive")
    found: dict[str, str] = {}
    for member in members:
        name = PurePosixPath(member.replace("\\", "/")).name.casefold()
        if name in wanted:
            if wanted[name] in found:
                raise UserFileError("ambiguous_files")
            found[wanted[name]] = member
    if len(found) != len(wanted):
        raise UserFileError("missing_files")
    return found


def _extract(path: Path, members: dict[str, str], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".dll":
        shutil.copyfile(path, destination / next(iter(members)))
        return
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for wanted, member in members.items():
                if archive.getinfo(member).file_size > MAX_MEMBER:
                    raise UserFileError("too_large")
                with archive.open(member) as source, open(destination / wanted, "wb") as target:
                    shutil.copyfileobj(source, target)
        return
    staging = Path(tempfile.mkdtemp(dir=destination, prefix=".unpack-"))
    try:
        result = subprocess.run(["bsdtar", "-xf", str(path), "-C", str(staging), "--", *members.values()],
                                capture_output=True, timeout=300, check=False)
        if result.returncode != 0:
            raise UserFileError("unreadable")
        for wanted, member in members.items():
            source = staging / member
            if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(staging.resolve()):
                raise UserFileError("unsafe_archive")
            if source.stat().st_size > MAX_MEMBER:
                raise UserFileError("too_large")
            os.replace(source, destination / wanted)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _version(dependency, path: Path, extracted: Path | None) -> str | None:
    if extracted is not None:
        for member in dependency.files.values():
            if (extracted / member).suffix.lower() == ".dll":
                version = _dll_version(extracted / member)
                if version:
                    return version
    return _filename_version(path.name)


def _readable(dependency, path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in (*ARCHIVES, ".dll"):
        raise UserFileError("unreadable")
    if path.stat().st_size > MAX_ARCHIVE:
        raise UserFileError("too_large")
    return _locate(dependency, path)


def inspect(dependency, path: Path) -> dict:
    """Whether this file is what the dependency asks for, with the version it carries."""
    path = Path(path)
    result = {"ok": False, "reason": None, "version": None, "filename": path.name}
    try:
        members = _readable(dependency, path)
        with tempfile.TemporaryDirectory(prefix="pdc-user-file-") as scratch:
            dll_members = {k: v for k, v in members.items() if k.lower().endswith(".dll")}
            extracted = None
            if dll_members:
                _extract(path, dll_members, Path(scratch))
                extracted = Path(scratch)
            result["version"] = _version(dependency, path, extracted)
    except UserFileError as error:
        result["reason"] = error.code
        return result
    except (OSError, zipfile.BadZipFile, KeyError, subprocess.SubprocessError, ValueError):
        result["reason"] = "unreadable"
        return result
    result["ok"] = True
    return result


_INSPECTED: dict[tuple, dict] = {}


def _inspect_cached(dependency, path: Path) -> dict:
    """inspect() once per file version: the download watcher asks again every few seconds."""
    try:
        stat = path.stat()
    except OSError:
        return inspect(dependency, path)
    key = (dependency.id, tuple(sorted(dependency.files.values())), str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _INSPECTED:
        if len(_INSPECTED) > 512:
            _INSPECTED.clear()
        _INSPECTED[key] = inspect(dependency, path)
    return _INSPECTED[key]


def candidates(dependency, folders) -> list[dict]:
    """Downloads that carry what the dependency asks for, newest first."""
    files: list[tuple[float, Path]] = []
    for folder in folders:
        try:
            for entry in os.scandir(folder):
                if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith((*ARCHIVES, ".dll")):
                    files.append((entry.stat().st_mtime, Path(entry.path)))
        except OSError:
            continue
    found = []
    for _, path in sorted(files, key=lambda item: -item[0])[:MAX_SCANNED]:
        checked = _inspect_cached(dependency, path)
        if checked["ok"]:
            found.append({"path": str(path), "filename": path.name, "version": checked["version"]})
            if len(found) >= MAX_CANDIDATES:
                break
    return found


def _state(dependency, version: str | None) -> str:
    if version and version in dependency.avoid_versions:
        return "avoid"
    if version and dependency.version and version != dependency.version:
        return "other_version"
    return "ready"


class Store:
    """The user's chosen file for each dependency, kept so reinstalling never asks again."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _folder(self, dependency) -> Path:
        return self.root / dependency.id

    def _meta(self, dependency) -> dict:
        try:
            data = json.loads((self._folder(dependency) / "meta.json").read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def status(self, dependency) -> dict:
        meta = self._meta(dependency)
        ready = bool(meta) and all((self._folder(dependency) / "files" / m).is_file() for m in dependency.files.values())
        return {
            "id": dependency.id, "name": dependency.name, "page_url": dependency.page_url,
            "download_url": getattr(dependency, "download_url", None) or dependency.page_url,
            "version": dependency.version, "installed_version": meta.get("version") if ready else None,
            "filename": meta.get("filename") if ready else None,
            "state": _state(dependency, meta.get("version")) if ready else "missing",
        }

    def sources(self, dependency) -> dict[str, Path]:
        if self.status(dependency)["state"] == "missing":
            return {}
        files = self._folder(dependency) / "files"
        return {destination: files / member for destination, member in dependency.files.items()}

    def adopt(self, dependency, path: Path) -> dict:
        path = Path(path)
        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=self.root, prefix=f".{dependency.id}-"))
        try:
            _extract(path, _readable(dependency, path), staging / "files")
            version = _version(dependency, path, staging / "files")
            (staging / "meta.json").write_text(json.dumps({"filename": path.name, "version": version, "at": time.time()}))
            old = self._folder(dependency)
            trash = None
            if old.exists():
                trash = self.root / f".{dependency.id}-old-{time.time_ns()}"
                os.replace(old, trash)
            os.replace(staging, old)
            if trash:
                shutil.rmtree(trash, ignore_errors=True)
        except (OSError, zipfile.BadZipFile, KeyError, subprocess.SubprocessError, ValueError):
            raise UserFileError("unreadable") from None
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return self.status(dependency)

    def remove(self, dependency) -> dict:
        shutil.rmtree(self._folder(dependency), ignore_errors=True)
        return self.status(dependency)
