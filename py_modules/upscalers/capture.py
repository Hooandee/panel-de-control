"""Game-only frames for the comparison, taken by gamescope (no Steam overlays in them)."""

import base64
import os
import shutil
import time
from pathlib import Path
from typing import Callable

from display.screen_sleep import gamescopectl

SHOT_TIMEOUT_S = 4.0
KEEP = 6

Run = Callable[..., tuple[int, str]]


class CaptureError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def take(folder: Path, name: str, run: Run = gamescopectl, scratch: str = "/tmp") -> Path:
    """Ask gamescope for a screenshot and move it into `folder`; gamescope writes as the session user."""
    folder.mkdir(parents=True, exist_ok=True)
    temporary = Path(scratch) / f"pdc-upscaler-{os.getpid()}-{time.monotonic_ns()}.png"
    rc, _ = run("screenshot", str(temporary))
    if rc != 0:
        raise CaptureError("capture_failed")
    deadline = time.monotonic() + SHOT_TIMEOUT_S
    last = -1
    while time.monotonic() < deadline:
        try:
            size = temporary.stat().st_size
        except OSError:
            size = -1
        if size > 0 and size == last:
            break
        last = size
        time.sleep(0.15)
    else:
        temporary.unlink(missing_ok=True)
        raise CaptureError("capture_failed")
    target = folder / f"{name}.png"
    shutil.move(str(temporary), target)
    for old in sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime)[:-KEEP]:
        old.unlink(missing_ok=True)
    return target


def data_url(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
