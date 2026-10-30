from __future__ import annotations

import hashlib
import errno
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional

from pdc_platform.host_env import clean_env

FRAME_RATES = (10, 15, 24, 30)
TIMEOUT_SEC = 900
_KNOWN_FFMPEG = ("/usr/bin/ffmpeg",)


class OptimizeError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Optimized:
    path: str
    encoder: str


def find_ffmpeg() -> Optional[str]:
    for candidate in _KNOWN_FFMPEG:
        if os.access(candidate, os.X_OK):
            return candidate
    return shutil.which("ffmpeg")


def needs_optimization(width: int, height: int, target_height: int) -> bool:
    return max(width, height) > 0 and height > target_height


def build_commands(ffmpeg: str, source: str, target: str, height: int, fps: int = 30) -> list[list[str]]:
    base = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    vaapi = base + [
        "-vaapi_device", "/dev/dri/renderD128", "-i", source,
        "-vf", f"scale=-2:{height},fps={fps},format=nv12,hwupload",
        "-c:v", "h264_vaapi", "-qp", "24", "-an", "-movflags", "+faststart", target,
    ]
    software = base + [
        "-i", source, "-vf", f"scale=-2:{height},fps={fps}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-an", "-movflags", "+faststart", target,
    ]
    return [vaapi, software]


def output_name(source: str, height: int, fps: int = 30) -> str:
    stat = os.stat(source)
    key = f"{os.path.realpath(source)}:{stat.st_size}:{int(stat.st_mtime)}:{height}" + ("" if fps == 30 else f":{fps}fps")
    return "opt-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".mp4"


def _background_priority() -> None:
    os.nice(15)


def _run(command: list[str], cancel: Optional[threading.Event]) -> int:
    """Runs one encode; killed when cancelled or past the timeout so it never outlives Ambiente."""
    try:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env={**clean_env(), "LC_ALL": "C"}, preexec_fn=_background_priority)
    except OSError as exc:
        if exc.errno in (errno.ENOSPC, errno.EDQUOT):
            raise OptimizeError("no_space") from exc
        return -1
    no_space = threading.Event()

    def read_errors() -> None:
        assert process.stderr is not None
        with process.stderr as errors:
            tail = b""
            while chunk := errors.read1(4096):
                text = tail + chunk.lower()
                if b"no space left on device" in text or b"disk quota exceeded" in text:
                    no_space.set()
                tail = text[-64:]

    reader = threading.Thread(target=read_errors, name="ambient-encode-errors", daemon=True)
    reader.start()
    deadline = time.monotonic() + TIMEOUT_SEC
    while True:
        try:
            code = process.wait(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if no_space.is_set() or (cancel is not None and cancel.is_set()) or time.monotonic() > deadline:
                process.kill()
                process.wait()
                code = -1
                break
    reader.join()
    if no_space.is_set():
        raise OptimizeError("no_space")
    return code


def optimize(source: str, cache_dir: str, height: int, cancel: Optional[threading.Event] = None, fps: int = 30) -> Optimized:
    """Re-encode a video once for the screen height and frame rate: hardware H.264 first, software second."""
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise OptimizeError("no_encoder")
    target = os.path.join(cache_dir, output_name(source, height, fps))
    if os.path.isfile(target):
        return Optimized(target, "cached")
    partial = target + ".part.mp4"
    try:
        os.makedirs(cache_dir, exist_ok=True)
        for command in build_commands(ffmpeg, source, partial, height, fps):
            encoder = command[command.index("-c:v") + 1]
            if cancel is not None and cancel.is_set():
                break
            code = _run(command, cancel)
            if code == 0 and os.path.isfile(partial) and os.path.getsize(partial) > 0:
                os.replace(partial, target)
                return Optimized(target, encoder)
            if os.path.exists(partial):
                os.unlink(partial)
        raise OptimizeError("cancelled" if cancel is not None and cancel.is_set() else "encode_failed")
    except OSError as exc:
        reason = "no_space" if exc.errno in (errno.ENOSPC, errno.EDQUOT) else "encode_failed"
        raise OptimizeError(reason) from exc
    finally:
        if os.path.exists(partial):
            os.unlink(partial)
