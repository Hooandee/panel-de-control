"""HelixSR through its own bridge and setup.

HelixSR's licence forbids modifying or redistributing its files, so Panel only
unpacks the official release into the user's HelixSR folder and drives it with
the JSON bridge HelixSR Desktop uses. Everything runs as the user who owns the
games, never as root, so the game folders keep their owner.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable

from user_session import session_for_uid, spawn_args

RELEASE = "HelixSR-3.2.0"
SCALER_VERSION = "2.1.0"
COMPLETE = ".panel-complete"
BRIDGE_TIMEOUT_S = 180
BUILD_TIMEOUT_S = 45 * 60
MAX_LOG_BYTES = 2 * 1024 * 1024

_SAY = re.compile(r"^\[helixsr-setup\]\s+(.+)$")
_DISPATCH = re.compile(r"render (\d{2,5})x(\d{2,5}) -> (\d{2,5})x(\d{2,5})")
_FFX = re.compile(r"FFX upscaler: (HLX [\w ]+?) \(")
_NETWORK_OFF = re.compile(r"network (?:is )?not running|red border", re.I)


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
        self.popen = subprocess.Popen

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
        if os.geteuid() != 0:
            return
        stat = self.home.stat()
        for path in [folder.parent, folder, *folder.rglob("*")]:
            os.chown(path, stat.st_uid, stat.st_gid, follow_symlinks=False)

    def status(self) -> dict:
        if not self.ready():
            return {"downloaded": False}
        answer = self._bridge("status")
        return {
            "downloaded": True,
            "version": answer.get("version"),
            "network": bool(answer.get("network_ready")),
            "hlx": answer.get("hlx_ready"),
        }

    def build(self, step: Callable[[str], None], cancelled: Callable[[], bool]) -> dict:
        """HelixSR's setup builds HLX DLSS's network once; --yes only after the user accepted NVIDIA's licence."""
        if not self.ready():
            raise HelixError("helixsr_missing")
        argv, extra = self._spawn(["bash", str(self.release / "helixsr-setup.sh"), "--yes"])
        try:
            process = self.popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 text=True, cwd=str(self.release), **extra)
        except OSError as error:
            raise HelixError("helixsr_build_failed", type(error).__name__) from None
        deadline = time.monotonic() + BUILD_TIMEOUT_S
        last = ""
        for line in process.stdout:
            if cancelled() or time.monotonic() > deadline:
                process.kill()
                raise HelixError("cancelled" if cancelled() else "helixsr_build_failed", last)
            said = _SAY.match(line.strip())
            if said:
                last = said.group(1)[:160]
                step(last)
        if process.wait(timeout=60) != 0:
            raise HelixError("helixsr_build_failed", last)
        return self.status()

    # ---- games ----------------------------------------------------------------
    def install(self, game: Path, way: str) -> dict:
        args = ["--game", str(game), "--way", way]
        if way == "scaler":
            args += ["--scaler", str(self.release / "helixsr-scaler"), "--scaler-version", SCALER_VERSION]
        return self._bridge("install", *args).get("game") or {}

    def remove(self, game: Path) -> dict:
        return self._bridge("remove", "--game", str(game)).get("game") or {}


def read_log(exe_folder: Path, logs: list[Path], since: float | None = None) -> dict:
    """What HelixSR did: its own dispatch lines, and HelixSR Scaler's choice of upscaler."""
    facts: dict = {"present": False}
    for path in [*logs, exe_folder / "OptiScaler.log"]:
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
            if match := _DISPATCH.search(line):
                facts["resolution"] = {
                    "render": [int(match.group(1)), int(match.group(2))],
                    "output": [int(match.group(3)), int(match.group(4))],
                }
            elif match := _FFX.search(line):
                facts["upscaler"] = match.group(1).strip()
            elif _NETWORK_OFF.search(line):
                facts["network_off"] = True
    return facts


def verdict(facts: dict) -> str:
    if not facts.get("present") or facts.get("stale"):
        return "not_run"
    if facts.get("resolution") and not facts.get("network_off"):
        return "active"
    return "loaded"
