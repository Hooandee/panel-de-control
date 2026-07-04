"""Thin busctl driver for InputPlumber (no python-dbus dependency; busctl ships
with systemd). Discovers the composite-device object path dynamically. Every call
degrades to a safe empty/False on failure — never raises.
"""
import json
import re
import subprocess

from controllers.detect import clean_env, resolve_bin

SVC = "org.shadowblip.InputPlumber"
IFACE = "org.shadowblip.Input.CompositeDevice"
DEFAULT_PROFILE_PATH = "/usr/share/inputplumber/profiles/default.yaml"


def _run(args, timeout: int = 6):
    # Resolve the binary absolutely + scrub the frozen-backend env (see detect.py).
    try:
        args = [resolve_bin(args[0]), *args[1:]]
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, env=clean_env()
        )
    except Exception:
        return None


def _composite_path(run) -> str | None:
    r = run(["busctl", "tree", SVC])
    if not r or r.returncode != 0:
        return None
    m = re.findall(r"(/org/shadowblip/InputPlumber/CompositeDevice\d+)", r.stdout)
    return m[0] if m else None


class IpDbus:
    """Drives the active CompositeDevice: read capabilities + current profile,
    load a remap profile, reset to default."""

    def __init__(self, run=_run):
        self._run = run
        self._cached_path = None

    def _path(self):
        # The composite object path is stable for the daemon's lifetime; discover it
        # once (a `busctl tree` spawn) and reuse — every method needs it, so this
        # roughly halves the busctl subprocesses per remap action.
        if self._cached_path is None:
            self._cached_path = _composite_path(self._run)
        return self._cached_path

    def _failed(self, r) -> bool:
        """A busctl call failed → drop the cached path: the composite device may have
        been recreated (e.g. InputPlumber restart → CompositeDevice1), so the next
        call re-discovers it instead of hammering a dead object forever."""
        if not r or r.returncode != 0:
            self._cached_path = None
            return True
        return False

    def capabilities(self) -> list:
        """The device's live capability strings (e.g. 'Gamepad:Button:RightPaddle1')."""
        path = self._path()
        if not path:
            return []
        r = self._run(["busctl", "get-property", SVC, path, IFACE, "Capabilities"])
        if self._failed(r):
            return []
        # Output: as <n> "cap" "cap" ...  → pull the quoted strings.
        return re.findall(r'"([^"]+)"', r.stdout)

    def get_profile_yaml(self) -> str | None:
        path = self._path()
        if not path:
            return None
        r = self._run(["busctl", "--json=short", "call", SVC, path, IFACE, "GetProfileYaml"])
        if self._failed(r):
            return None
        try:
            return json.loads(r.stdout)["data"][0]
        except Exception:
            return None

    def load_profile_yaml(self, yaml: str) -> bool:
        path = self._path()
        if not path:
            return False
        r = self._run(["busctl", "call", SVC, path, IFACE, "LoadProfileFromYaml", "s", yaml])
        return not self._failed(r)

    def reset_default(self) -> bool:
        path = self._path()
        if not path:
            return False
        r = self._run(["busctl", "call", SVC, path, IFACE, "LoadProfilePath", "s", DEFAULT_PROFILE_PATH])
        return not self._failed(r)
