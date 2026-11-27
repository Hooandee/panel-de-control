"""A mod the user brings for one game (an archive from Nexus or Patreon). Panel keeps a copy and installs its files
beside the game's exe together with OptiScaler, through the same manifest, so turning the upscaler off takes them out.
Nothing in the archive is ever run."""

import fnmatch
from functools import lru_cache
import json
import os
import re
import shutil
import stat
from struct import error as struct_error
import subprocess
import tempfile
import time
import zipfile
import zlib
from pathlib import Path, PurePosixPath

from . import games, pe, user_deps
from .assets import sha256

MAX_FILES = 400
MAX_TOTAL = 2 * 1024 * 1024 * 1024
PREVIEW = 8
# Where to get the mod a game's wiki entry asks for, when it is a free download.
DOWNLOADS = {
    "1245620": "https://www.patreon.com/huutaiii/posts/erss-fg-free-v4-125972766",  # Elden Ring: ERSS-FG
}
# A mod's DLL with one of these names replaces a Windows library, which Proton only loads with a native override.
SYSTEM_DLLS = frozenset({
    "d3d9", "d3d10", "d3d10_1", "d3d10core", "d3d11", "d3d12", "d3d12core", "dxgi", "dinput8", "dsound", "version",
    "winmm", "winhttp", "wininet", "dbghelp", "xinput1_3", "xinput1_4", "xinput9_1_0", "opengl32",
})
# Files Panel's OptiScaler installs: a mod carrying its own would replace them, so it is refused when added.
OPTISCALER_FILES = ("optiscaler.ini", "optiscaler.dll", "optiscaler.log", "optiscaler/*", "nvngx.dll", "nvngx_dlss.dll",
                    "libxess*.dll", "amd_fidelityfx_*.dll", "amdxcffx64.dll", "fakenvapi*", "nvapi64.dll",
                    "dlssg_to_fsr3*", "d3d12_optiscaler/*")


class ModError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _parts(member: str) -> tuple[str, ...]:
    return PurePosixPath(member.replace("\\", "/")).parts


def _fold(parts) -> tuple[str, ...]:
    return tuple(part.casefold() for part in parts)


def layout(members: list[str], target: str, existing: set[str] | None = None, root_dirs: set[str] | None = None) -> dict[str, str]:
    """Where each archive member goes, relative to the exe's folder (`target`, relative to the game root).

    A single wrapping folder the game doesn't have (`ERSS-FG 1.2/…`) is dropped, then the game's own path down to the
    exe's folder (`Game/eldenring.exe` → `Game/…`). A mod that also reaches elsewhere in the game (another folder of the
    game root) can't be laid out beside the exe and is refused.
    """
    existing = {name.casefold() for name in (existing or set())}
    root_dirs = {name.casefold() for name in (root_dirs or set())}
    paths = [_parts(member) for member in members]
    if not paths:
        raise ModError("empty")
    prefix = _fold(part for part in PurePosixPath(target).parts if part not in ("", "."))
    if all(len(p) > 1 for p in paths) and len({p[0].casefold() for p in paths}) == 1 \
            and paths[0][0].casefold() not in existing and paths[0][0].casefold() not in root_dirs:
        paths = [p[1:] for p in paths]
    if prefix and all(len(p) > len(prefix) and _fold(p[:len(prefix)]) == prefix for p in paths):
        paths = [p[len(prefix):] for p in paths]
    elif any(len(p) > 1 and p[0].casefold() in root_dirs and p[0].casefold() not in existing for p in paths):
        raise ModError("layout")
    result: dict[str, str] = {}
    seen: set[str] = set()
    for member, parts in zip(members, paths):
        destination = PurePosixPath(*parts).as_posix()
        if destination.casefold() in seen:
            raise ModError("ambiguous_files")
        seen.add(destination.casefold())
        result[destination] = member
    return result


# DLLs from the Visual C++ runtime: a mod built against a recent one (ERSS-FG 4.14 dropped its static copy) hangs on
# Proton's older msvcp140 until the prefix gets vcrun2022.
_VC_RUNTIME = ("msvcp140", "vcruntime140", "concrt140")


def prefix_verbs(folder: Path, destinations) -> list[str]:
    """Windows components the mod's DLLs need in the game's Proton prefix."""
    for name in destinations:
        if not name.lower().endswith((".dll", ".asi")):
            continue
        try:
            imported = pe.imported_dlls(str(folder / name))
        except (OSError, ValueError, struct_error):
            continue
        if any(dll.startswith(_VC_RUNTIME) for dll in imported):
            return ["vcrun2022"]
    return []


_ERSS_DLL = "erss-fg.dll"
_ERSS_SETTINGS = "ERSS2/ERSS-FG.toml"
_ERSS_HEADER = b"# Version: 4.14.1-0 (86498e0) Release"
_ERSS_VERSION = frozenset({"4.14.1", "4.14.1.0", "4.14.1-0"})
_ERSS_REVISION = re.compile(rb"(?<![a-zA-Z0-9])86498e0(?![a-zA-Z0-9])")
_ERSS_FILES = {
    _ERSS_DLL: 14648832,
    "d3d12.dll": 521216,
    "erssreshadestub.addon": 455168,
    "erss2/bin/amd_fidelityfx_framegeneration_dx12.dll": 38245640,
    "erss2/bin/amd_fidelityfx_loader_dx12.dll": 25864,
    "erss2/bin/amd_fidelityfx_upscaler_dx12.dll": 22348552,
}


def _file_stamp(path: Path) -> tuple[int, ...]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("not_regular")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@lru_cache(maxsize=32)
def _erss_binary(path: Path, stamp: tuple[int, ...]) -> bool | None:
    imports = pe.imported_dlls(str(path))
    if not any(dll.startswith(_VC_RUNTIME) for dll in imports):
        return False
    versions = pe.version_strings(str(path))
    reported = [versions[key] for key in ("ProductVersion", "FileVersion") if versions.get(key)]
    if reported:
        return any(version in _ERSS_VERSION for version in reported)
    with path.open("rb") as handle:
        binary = handle.read(_ERSS_FILES[_ERSS_DLL] + 1)
    return True if _ERSS_REVISION.search(binary) else None


@lru_cache(maxsize=32)
def _mod_digest(path: Path, stamp: tuple[int, ...]) -> str:
    return sha256(path)


def _erss_runtime(dll: Path, relative: str, stamp: tuple[int, ...], install: dict) -> bool:
    target_path = install.get("target")
    installed_at = install.get("installed_at")
    if not isinstance(target_path, str) or not isinstance(installed_at, (float, int)):
        return False
    target = Path(target_path)
    config = target / _ERSS_SETTINGS
    receipt = target / games.MANIFEST_DIR / "manifest.json"
    if not target.is_absolute() or config.parent.is_symlink() or receipt.parent.is_symlink():
        return False
    if _file_stamp(config)[3] <= installed_at * 1e9:
        return False
    with config.open("rb") as handle:
        if handle.readline(len(_ERSS_HEADER) + 3).rstrip(b"\r\n") != _ERSS_HEADER:
            return False
    if _file_stamp(receipt)[2] > 1024 * 1024:
        return False
    manifest = json.loads(receipt.read_text())
    if not isinstance(manifest, dict) or manifest.get("incomplete"):
        return False
    files = manifest.get("files")
    owned = manifest.get("owned")
    if not isinstance(files, dict) or not isinstance(owned, list) or relative not in owned:
        return False
    installed = target / relative
    installed_stamp = _file_stamp(installed)
    return (installed_stamp[2] == _ERSS_FILES[_ERSS_DLL] and
            files.get(relative) == _mod_digest(dll, stamp) == _mod_digest(installed, installed_stamp))


def _tested_release(folder: Path, files: list[str], meta: dict, install: dict | None) -> str | None:
    by_name = {name.casefold(): name for name in files}
    if meta.get("target") != "Game" or not meta.get("id") or not _ERSS_FILES.keys() <= by_name.keys():
        return None
    try:
        if any(_file_stamp(folder / by_name[name])[2] != size for name, size in _ERSS_FILES.items()):
            return None
        relative = by_name[_ERSS_DLL]
        dll = folder / relative
        stamp = _file_stamp(dll)
        has_version = _erss_binary(dll, stamp)
        if has_version is False:
            return None
        if has_version:
            return "erss-fg-4.14.1"
        installed_mod = (install or {}).get("mod")
        if isinstance(installed_mod, dict) and installed_mod.get("id") == meta["id"] and _erss_runtime(
                dll, relative, stamp, install):
            return "erss-fg-4.14.1"
    except (OSError, ValueError, struct_error):
        return None
    return None


def replaces_optiscaler(destinations) -> bool:
    return any(fnmatch.fnmatch(d.casefold(), pattern) for d in destinations for pattern in OPTISCALER_FILES)


def native_dlls(destinations) -> list[str]:
    """System libraries the mod puts beside the exe, which need `name=n,b` in WINEDLLOVERRIDES."""
    return sorted({PurePosixPath(d).stem.lower() for d in destinations
                   if "/" not in d and d.lower().endswith(".dll") and PurePosixPath(d).stem.lower() in SYSTEM_DLLS})


def _seven_zip() -> bool:
    """7z reads every 7-Zip method and password-protected archives (Patreon mods often are); bsdtar doesn't."""
    return bool(shutil.which("7z")) or os.path.isabs(user_deps.resolve_bin("7z"))


def _entries(path: Path, password: str | None = None) -> tuple[list[tuple[str, int]], bool]:
    """Files in the archive with their sizes, and whether they are encrypted, read before anything is extracted;
    links are refused."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            entries = []
            encrypted = False
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ModError("unsafe_archive")
                encrypted |= bool(info.flag_bits & 0x1)
                entries.append((info.filename, info.file_size))
            return entries, encrypted
    if _seven_zip():
        # -p always: an archive with encrypted names otherwise waits for a password on stdin.
        result = user_deps.run_archiver(["7z", "l", "-slt", "-ba", f"-p{password or ''}", str(path.resolve())], 60)
        if result.returncode != 0:
            said = (result.stdout + result.stderr).decode("utf-8", "replace").lower()
            if "wrong password" in said or "encrypted" in said:
                raise ModError("password_wrong" if password else "password")
            raise ModError("unreadable")
        entries = []
        encrypted = False
        for block in result.stdout.decode("utf-8", "replace").replace("\r", "").split("\n\n"):
            fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
            if not fields.get("Path") or fields.get("Folder") == "+" or fields.get("Attributes", "").startswith("D"):
                continue
            mode = fields.get("Attributes", "").partition(" ")[2].lstrip("-")
            if mode.startswith("l") or fields.get("Symbolic Link"):
                raise ModError("unsafe_archive")
            encrypted |= fields.get("Encrypted") == "+"
            entries.append((fields["Path"], int(fields.get("Size") or 0)))
        return entries, encrypted
    result = user_deps.run_archiver(["bsdtar", "-tvf", str(path.resolve())], 60)
    if result.returncode != 0:
        raise ModError("unreadable")
    entries = []
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        fields = line.split(None, 8)
        if len(fields) < 9 or fields[0].startswith("d"):
            continue
        if not fields[0].startswith("-"):
            raise ModError("unsafe_archive")
        entries.append((fields[8], int(fields[4])))
    # bsdtar can't tell encryption apart in a listing; extracting then fails and says so.
    return entries, False


def _readable(path: Path, password: str | None = None) -> list[str]:
    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in user_deps.ARCHIVES:
        raise ModError("unreadable")
    if path.stat().st_size > user_deps.MAX_ARCHIVE:
        raise ModError("too_large")
    try:
        entries, encrypted = _entries(path, password)
    except ModError:
        raise
    except (OSError, zipfile.BadZipFile, subprocess.SubprocessError, ValueError):
        raise ModError("unreadable") from None
    members = [name for name, _ in entries]
    if any(user_deps._unsafe(member) for member in members):
        raise ModError("unsafe_archive")
    if len(members) > MAX_FILES:
        raise ModError("too_many_files")
    if any(size > user_deps.MAX_MEMBER for _, size in entries) or sum(size for _, size in entries) > MAX_TOTAL:
        raise ModError("too_large")
    if encrypted and not password:
        raise ModError("password")
    return members


def _extract_all(path: Path, wanted: dict[str, str], destination: Path, password: str | None = None) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for target, member in wanted.items():
                out = destination / target
                out.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with archive.open(member, pwd=password.encode() if password else None) as source, open(out, "wb") as sink:
                        shutil.copyfileobj(source, sink)
                except (RuntimeError, zipfile.BadZipFile, zlib.error):
                    raise ModError("password_wrong" if password else "password") from None
                except NotImplementedError:
                    raise ModError("unreadable") from None
        return
    staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=".unpack-"))
    try:
        if _seven_zip():
            command = ["7z", "x", "-y", f"-p{password or ''}", f"-o{staging}", str(path.resolve())]
        else:
            command = ["bsdtar", "-xf", str(path.resolve()), "-C", str(staging)]
        try:
            done = user_deps.run_archiver(command, 600)
        except subprocess.TimeoutExpired:
            raise ModError("unreadable") from None
        if done.returncode != 0:
            said = (done.stdout + done.stderr).decode("utf-8", "replace").lower()
            if "wrong password" in said or "encrypted" in said:
                raise ModError("password_wrong" if password else "password")
            raise ModError("unreadable")
        if any(found.is_symlink() for found in staging.rglob("*")):
            raise ModError("unsafe_archive")
        for target, member in wanted.items():
            source = staging / member
            if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(staging.resolve()):
                raise ModError("unsafe_archive")
            out = destination / target
            out.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, out)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


PARTIAL = (".crdownload", ".part", ".download", ".tmp")


def downloading(folders) -> dict | None:
    """The download still being written (Steam's browser shows no progress), newest first."""
    found = []
    for folder in folders:
        try:
            for entry in os.scandir(folder):
                if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(PARTIAL):
                    info = entry.stat()
                    if time.time() - info.st_mtime < 60:
                        found.append((info.st_mtime, entry.name, info.st_size))
        except OSError:
            continue
    if not found:
        return None
    _, name, size = max(found)
    return {"filename": name, "size": size}


def candidates(folders, limit: int = 6) -> list[dict]:
    """Archives in Downloads, newest first. A mod has no fixed content to check, so the user picks it; the size lets
    a download watcher wait until the file stops growing."""
    found = []
    for folder in folders:
        try:
            for entry in os.scandir(folder):
                if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(user_deps.ARCHIVES):
                    info = entry.stat()
                    found.append((info.st_mtime, entry.path, info.st_size))
        except OSError:
            continue
    return [{"path": path, "filename": Path(path).name, "size": size} for _, path, size in sorted(found, reverse=True)[:limit]]


class Store:
    """One mod per game, kept so a reinstall or a new upscaler version never asks again."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _folder(self, appid: str) -> Path:
        if not str(appid).isalnum():
            raise ModError("unreadable")
        return self.root / str(appid)

    def _meta(self, appid: str) -> dict:
        try:
            data = json.loads((self._folder(appid) / "meta.json").read_text())
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) and isinstance(data.get("files"), list) else {}

    def status(self, appid: str, *, install: dict | None = None) -> dict | None:
        meta = self._meta(appid)
        folder = self._folder(appid) / "files"
        files = [f for f in meta.get("files", []) if isinstance(f, str)]
        if not files or not all((folder / f).is_file() for f in files):
            return None
        status = {"filename": meta.get("filename"), "id": meta.get("id"), "target": meta.get("target"), "count": len(files),
                  "files": files[:PREVIEW], "native_dlls": native_dlls(files),
                  "verbs": [v for v in meta.get("verbs", []) if v == "vcrun2022"]}
        if str(appid) == "1245620" and (release := _tested_release(folder, files, meta, install)):
            status["tested_release"] = release
        return status

    def sources(self, appid: str) -> dict[str, Path]:
        if self.status(appid) is None:
            return {}
        folder = self._folder(appid) / "files"
        return {name: folder / name for name in self._meta(appid)["files"]}

    def adopt(self, appid: str, path: Path, target: str, existing: set[str], root_dirs: set[str],
              password: str | None = None) -> dict:
        path = Path(path)
        self._folder(appid)
        members = _readable(path, password)
        wanted = layout(members, target, existing, root_dirs)
        if replaces_optiscaler(wanted):
            raise ModError("conflict")
        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=self.root, prefix=f".{appid}-"))
        try:
            _extract_all(path, wanted, staging / "files", password)
            (staging / "meta.json").write_text(json.dumps({
                "filename": path.name, "files": sorted(wanted), "target": target, "id": f"{path.name}@{time.time_ns()}",
                "verbs": prefix_verbs(staging / "files", wanted),
            }))
            old = self._folder(appid)
            trash = None
            if old.exists():
                trash = self.root / f".{appid}-old-{time.time_ns()}"
                os.replace(old, trash)
            os.replace(staging, old)
            if trash:
                shutil.rmtree(trash, ignore_errors=True)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return self.status(appid) or {}

    def remove(self, appid: str) -> None:
        shutil.rmtree(self._folder(appid), ignore_errors=True)
