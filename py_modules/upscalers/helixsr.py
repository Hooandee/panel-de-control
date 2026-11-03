"""HelixSR through its own bridge and setup.

HelixSR's licence forbids modifying or redistributing its files, so Panel only
unpacks the official release into the user's HelixSR folder and drives it with
the JSON bridge HelixSR Desktop uses. Only HLX FSR 4 (the FSR drop-in, built from
AMD's MIT FSR SDK) is used; HLX DLSS is left out on purpose because building it
takes NVIDIA's DLSS DLL apart for AMD GPUs, against NVIDIA's licence. Everything
runs as the user who owns the games, never as root.
"""

import json
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
        self.release = self.home / ".local/share/HelixSR/panel" / RELEASE
        self.run = subprocess.run

    def ready(self) -> bool:
        return (self.release / COMPLETE).is_file()

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
    def unpack(self, archive: Path) -> None:
        """Extract the official ZIP's release folder as it is; nothing else it carries."""
        parent = self.release.parent
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=parent, prefix=".unpack-"))
        prefix = f"{RELEASE}/"
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
            (staging / COMPLETE).write_text(RELEASE)
            self._own(staging)
            shutil.rmtree(self.release, ignore_errors=True)
            os.replace(staging, self.release)
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
            facts.setdefault("stale", True)
            continue
        facts["present"] = True
        facts.pop("stale", None)
        for line in text.splitlines():
            if match := _HLX_FSR.search(line):
                facts["upscaler"] = "HLX FSR 4"
                facts["output"] = [int(match.group(1)), int(match.group(2))]
    return facts


def verdict(facts: dict) -> str:
    if not facts.get("present") or facts.get("stale"):
        return "not_run"
    return "active" if facts.get("upscaler") else "loaded"
