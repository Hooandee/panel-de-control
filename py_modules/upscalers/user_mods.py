"""A mod the user brings for one game (an archive from Nexus or Patreon). Panel keeps a copy and installs its files
beside the game's exe together with OptiScaler, through the same manifest, so turning the upscaler off takes them out.
Nothing in the archive is ever run."""

import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

from . import user_deps

MAX_FILES = 400
MAX_TOTAL = 2 * 1024 * 1024 * 1024
PREVIEW = 8
# A mod's DLL with one of these names replaces a Windows library, which Proton only loads with a native override.
SYSTEM_DLLS = frozenset({
    "d3d9", "d3d10", "d3d10_1", "d3d10core", "d3d11", "d3d12", "d3d12core", "dxgi", "dinput8", "dsound", "version",
    "winmm", "winhttp", "wininet", "dbghelp", "xinput1_3", "xinput1_4", "xinput9_1_0", "opengl32",
})


class ModError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _parts(member: str) -> tuple[str, ...]:
    return PurePosixPath(member.replace("\\", "/")).parts


def layout(members: list[str], target: str, existing: set[str] | None = None) -> dict[str, str]:
    """Where each archive member goes, relative to the exe's folder (`target`, relative to the game root).

    An archive mirroring the game (`Game/eldenring.exe` → `Game/…`) drops the path down to the exe's folder; a single
    wrapping folder the game doesn't have (`ERSS-FG 1.2/…`) is dropped too.
    """
    existing = {name.casefold() for name in (existing or set())}
    paths = [_parts(member) for member in members]
    if not paths:
        raise ModError("empty")
    prefix = tuple(part for part in PurePosixPath(target).parts if part not in ("", "."))
    if prefix and all(len(p) > len(prefix) and tuple(x.casefold() for x in p[:len(prefix)]) == tuple(x.casefold() for x in prefix) for p in paths):
        paths = [p[len(prefix):] for p in paths]
    elif all(len(p) > 1 for p in paths) and len({p[0].casefold() for p in paths}) == 1 and paths[0][0].casefold() not in existing:
        paths = [p[1:] for p in paths]
    result: dict[str, str] = {}
    seen: set[str] = set()
    for member, parts in zip(members, paths):
        destination = PurePosixPath(*parts).as_posix()
        if destination.casefold() in seen:
            raise ModError("ambiguous_files")
        seen.add(destination.casefold())
        result[destination] = member
    return result


def native_dlls(destinations) -> list[str]:
    """System libraries the mod puts beside the exe, which need `name=n,b` in WINEDLLOVERRIDES."""
    return sorted({PurePosixPath(d).stem.lower() for d in destinations
                   if "/" not in d and d.lower().endswith(".dll") and PurePosixPath(d).stem.lower() in SYSTEM_DLLS})


def _readable(path: Path) -> list[str]:
    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in user_deps.ARCHIVES:
        raise ModError("unreadable")
    if path.stat().st_size > user_deps.MAX_ARCHIVE:
        raise ModError("too_large")
    try:
        members = user_deps._members(path)
    except (OSError, zipfile.BadZipFile, subprocess.SubprocessError, ValueError):
        raise ModError("unreadable") from None
    if any(user_deps._unsafe(member) for member in members):
        raise ModError("unsafe_archive")
    if len(members) > MAX_FILES:
        raise ModError("too_many_files")
    return members


def _extract_all(path: Path, wanted: dict[str, str], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for target, member in wanted.items():
                size = archive.getinfo(member).file_size
                total += size
                if size > user_deps.MAX_MEMBER or total > MAX_TOTAL:
                    raise ModError("too_large")
                out = destination / target
                out.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, open(out, "wb") as sink:
                    shutil.copyfileobj(source, sink)
        return
    staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=".unpack-"))
    try:
        if user_deps._archiver() == "7z":
            command = ["7z", "x", "-y", f"-o{staging}", str(path.resolve())]
        else:
            command = ["bsdtar", "-xf", str(path.resolve()), "-C", str(staging)]
        if subprocess.run(command, capture_output=True, timeout=600, check=False).returncode != 0:
            raise ModError("unreadable")
        for target, member in wanted.items():
            source = staging / member
            if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(staging.resolve()):
                raise ModError("unsafe_archive")
            total += source.stat().st_size
            if source.stat().st_size > user_deps.MAX_MEMBER or total > MAX_TOTAL:
                raise ModError("too_large")
            out = destination / target
            out.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, out)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def candidates(folders, limit: int = 6) -> list[dict]:
    """Archives in Downloads, newest first. A mod has no fixed content to check, so the user picks it."""
    found = []
    for folder in folders:
        try:
            for entry in os.scandir(folder):
                if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(user_deps.ARCHIVES):
                    found.append((entry.stat().st_mtime, entry.path))
        except OSError:
            continue
    return [{"path": path, "filename": Path(path).name} for _, path in sorted(found, reverse=True)[:limit]]


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

    def status(self, appid: str) -> dict | None:
        meta = self._meta(appid)
        files = [f for f in meta.get("files", []) if isinstance(f, str)]
        if not files or not all((self._folder(appid) / "files" / f).is_file() for f in files):
            return None
        return {"filename": meta.get("filename"), "count": len(files), "files": files[:PREVIEW],
                "native_dlls": native_dlls(files), "at": meta.get("at")}

    def sources(self, appid: str) -> dict[str, Path]:
        status = self.status(appid)
        if status is None:
            return {}
        folder = self._folder(appid) / "files"
        return {name: folder / name for name in self._meta(appid)["files"]}

    def adopt(self, appid: str, path: Path, target: str, existing: set[str]) -> dict:
        path = Path(path)
        members = _readable(path)
        wanted = layout(members, target, existing)
        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=self.root, prefix=f".{appid}-"))
        try:
            _extract_all(path, wanted, staging / "files")
            (staging / "meta.json").write_text(json.dumps({"filename": path.name, "files": sorted(wanted), "at": time.time()}))
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
