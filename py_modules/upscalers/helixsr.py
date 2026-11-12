"""HelixSR through its own bridge and setup.

HelixSR's licence forbids modifying or redistributing its files, so Panel only
unpacks the official release into the user's HelixSR folder and drives it with
the JSON bridge HelixSR Desktop uses. Only HLX FSR 4 (the FSR drop-in, built from
AMD's MIT FSR SDK) is used; HLX DLSS is left out on purpose because building it
takes NVIDIA's DLSS DLL apart for AMD GPUs, against NVIDIA's licence. Everything
runs as the user who owns the games, never as root.
"""

import json
import mmap
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from user_session import session_for_uid, spawn_args

from . import ownership

RELEASE = "HelixSR-3.2.0"
COMPLETE = ".panel-complete"
CURRENT = "current"
BRIDGE_TIMEOUT_S = 180
MAX_LOG_BYTES = 2 * 1024 * 1024

# HLX FSR 4 logs its context once with the largest render size the game may send (Stellar Blade on
# Performance still reports 1280x800), so it proves HLX runs but not the real input size.
_HLX_FSR = re.compile(r"HLX-FSR-4 own runtime active: .*?output (\d{2,5})x(\d{2,5}), max render (\d{2,5})x(\d{2,5})")
HLX_FSR_LOG = "HLX_FSR.log"


class HelixError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


class HelixSR:
    def __init__(self, home: str):
        self.home = Path(home)
        self.root = self.home / ".local/share/HelixSR/panel"
        self.release = self._current()
        self.run = subprocess.run

    def _current(self) -> Path:
        try:
            name = (self.root / CURRENT).read_text().strip()
        except OSError:
            name = ""
        return self.root / (name if re.fullmatch(r"HelixSR-\d+\.\d+\.\d+", name) else RELEASE)

    def ready(self) -> bool:
        return (self.release / COMPLETE).is_file()

    def digest(self) -> str | None:
        """SHA-256 of the archive this release came from; None for one unpacked before Panel recorded it."""
        try:
            value = (self.release / COMPLETE).read_text().strip()
        except OSError:
            return None
        return value if re.fullmatch(r"[0-9a-f]{64}", value) else None

    # ---- running HelixSR's own tools as the user -----------------------------
    def _spawn(self, argv: list[str]) -> tuple[list[str], dict]:
        try:
            uid = self.home.stat().st_uid
        except OSError:
            uid = os.getuid()
        session = session_for_uid(uid) if os.geteuid() == 0 else None
        if session is None:
            return argv, {"env": {**os.environ, "HOME": str(self.home)}}
        command, env, identity = spawn_args(session, argv)
        return command, {"env": env, **identity}

    def _bridge(self, command: str, *args: str) -> dict:
        if not self.ready():
            raise HelixError("helixsr_missing")
        argv, extra = self._spawn(
            ["python3", str(self.release / "setup/helixsr_bridge.py"), str(self.release), command, *args])
        try:
            done = self.run(argv, capture_output=True, text=True, timeout=BRIDGE_TIMEOUT_S, cwd=str(self.release), **extra)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise HelixError("helixsr_failed", type(error).__name__) from None
        lines = [line for line in (done.stdout or "").splitlines() if line.startswith("{")]
        try:
            answer = json.loads(lines[-1])
        except (IndexError, ValueError):
            raise HelixError("helixsr_failed", (done.stderr or "").strip()[-200:]) from None
        if not answer.get("ok"):
            raise HelixError("helixsr_failed", str(answer.get("error") or "")[:200])
        return answer

    # ---- release --------------------------------------------------------------
    def unpack(self, archive: Path, digest: str = "") -> None:
        """Extract the official ZIP's release folder as it is; nothing else it carries."""
        name = Path(archive).stem
        if not re.fullmatch(r"HelixSR-\d+\.\d+\.\d+", name):
            name = RELEASE
        release = self.root / name
        parent = self.root
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=parent, prefix=".unpack-"))
        prefix = f"{name}/"
        try:
            with zipfile.ZipFile(archive) as zipped:
                for info in zipped.infolist():
                    if not info.filename.startswith(prefix) or info.is_dir():
                        continue
                    relative = Path(info.filename[len(prefix):])
                    if relative.is_absolute() or ".." in relative.parts:
                        raise HelixError("unsafe_archive")
                    destination = staging / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with zipped.open(info) as source, open(destination, "wb") as out:
                        shutil.copyfileobj(source, out)
            if not (staging / "setup/helixsr_bridge.py").is_file():
                raise HelixError("unpack_failed", "bridge missing")
            (staging / COMPLETE).write_text(digest or name)
            self._own(staging)
            shutil.rmtree(release, ignore_errors=True)
            os.replace(staging, release)
            (parent / CURRENT).write_text(name)
            previous, self.release = self.release, release
            if previous != release and previous.parent == parent:
                shutil.rmtree(previous, ignore_errors=True)
        except (zipfile.BadZipFile, OSError) as error:
            raise HelixError("unpack_failed", type(error).__name__) from None
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _own(self, folder: Path) -> None:
        ownership.own_like(self.home, [folder.parent, folder])

    # ---- games ----------------------------------------------------------------
    def install(self, game: Path) -> dict:
        return self._bridge("install", "--game", str(game), "--way", "fsr").get("game") or {}

    def remove(self, game: Path) -> dict:
        return self._bridge("remove", "--game", str(game)).get("game") or {}


_RECORD = "helixsr-install.json"


def _recorded_swaps(folder: Path) -> list[tuple[Path, Path]]:
    """(game file, HelixSR's *.original.dll backup of it) for each file HelixSR's record says it replaced."""
    try:
        record = json.loads((folder / _RECORD).read_text())
    except (OSError, ValueError):
        record = {}
    names = record.get("files", []) if isinstance(record, dict) else []
    return [(folder / name, folder / Path(name).with_suffix(".original.dll").name)
            for name in names if isinstance(name, str) and "/" not in name]


def _drop_record(folder: Path) -> None:
    for name in (_RECORD, "helixsr.ini"):
        (folder / name).unlink(missing_ok=True)


def remove_by_hand(folder: Path) -> None:
    """When HelixSR's release is gone (deleted, or a newer Panel ships another), put the game's FSR back from
    the *.original.dll HelixSR's drop-in keeps, as its bridge would."""
    for current, original in _recorded_swaps(folder):
        if original.is_file():
            os.replace(original, current)
    _drop_record(folder)


def not_installed(detail: str) -> bool:
    """The bridge's answer when the game no longer has HelixSR's files (its own update put its FSR back)."""
    return bool(re.match(r"HelixSR( Scaler)? is not installed in ", detail or ""))


# Strings HelixSR's drop-in carries (its own log lines); AMD's FidelityFX DLLs never do.
_HELIX_SIGNATURES = (b"HLX-FSR-4", b"HelixSR")


def _is_helix_file(path: Path) -> bool:
    try:
        with open(path, "rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
            return any(data.find(signature) >= 0 for signature in _HELIX_SIGNATURES)
    except (OSError, ValueError):
        return False


def still_swapped(folder: Path) -> bool:
    """Whether a file HelixSR's record lists is still HelixSR's own DLL, whatever its bridge answered."""
    return any(_is_helix_file(current) for current, _ in _recorded_swaps(folder))


def forget(folder: Path) -> None:
    """Drop HelixSR's own record when its files are already gone. The game's files stay as they are; a backup is
    deleted only when it is byte for byte the file the game has now, so nothing that differs is lost."""
    for current, original in _recorded_swaps(folder):
        try:
            if (original.is_file() and not original.is_symlink() and not current.is_symlink()
                    and original.stat().st_size == current.stat().st_size
                    and original.read_bytes() == current.read_bytes()):
                original.unlink()
        except OSError:
            continue
    _drop_record(folder)


def read_install_log(install: dict) -> dict:
    if install.get("engine") != "helixsr":
        return {"present": False}
    logs = [Path(install["log"])] if install.get("log") else []
    since = install.get("installed_at")
    if since is not None and install.get("target") and install.get("helix_file"):
        root = Path(install["target"])
        storage = root / "_storage_"
        runtime = storage / HLX_FSR_LOG
        if (Path(install["helix_file"]).is_file()
                and (storage / "amd_fidelityfx_upscaler_dx12.dll").is_file()
                and runtime.resolve().is_relative_to(root.resolve())):
            logs.append(runtime)
    return read_log(logs, since=since)


def read_log(logs: list[Path], since: float | None = None) -> dict:
    """HLX FSR 4 writes one line per context it creates; it proves HLX runs, not how far it scales."""
    facts: dict = {"present": False}
    for path in dict.fromkeys([*logs, *(log.with_name(HLX_FSR_LOG) for log in logs)]):
        try:
            stat = path.stat()
            with open(path, "rb") as handle:
                if stat.st_size > MAX_LOG_BYTES:
                    handle.seek(stat.st_size - MAX_LOG_BYTES)
                text = handle.read().decode("utf-8", "replace")
        except OSError:
            continue
        if since is not None and stat.st_mtime < since:
            if not facts["present"]:
                facts["stale"] = True
            continue
        facts["present"] = True
        facts.pop("stale", None)
        facts.setdefault("path", str(path))
        for line in text.splitlines():
            if match := _HLX_FSR.search(line):
                facts["upscaler"] = "HLX FSR 4"
                facts["path"] = str(path)
                facts["output"] = [int(match.group(1)), int(match.group(2))]
    return facts


def verdict(facts: dict) -> str:
    if not facts.get("present") or facts.get("stale"):
        return "not_run"
    return "active" if facts.get("upscaler") else "loaded"
