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
_CAPABILITY_LIMIT = 64


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

    def __init__(self, run=_run, event_cb=None):
        self._run = run
        self._event_cb = event_cb
        self._cached_path = None
        self._last_capabilities = []
        self._last_reported_capabilities = None
        self._discovery_failures = 0
        self._last_operation = None

    @staticmethod
    def _is_logarithmic_sample(count):
        return count > 0 and count & (count - 1) == 0

    def _record(self, operation, ok, emit=True, **details):
        event = {"operation": operation, "ok": bool(ok), **details}
        self._last_operation = event
        if self._event_cb is None or not emit:
            return
        try:
            self._event_cb(dict(event))
        except Exception:  # noqa: BLE001 - diagnostics must not break controller I/O
            pass

    def diagnostics(self):
        diagnostic_capabilities = sorted(
            self._last_capabilities,
            key=lambda capability: (
                not capability.startswith("Gamepad:"),
                capability,
            ),
        )[:_CAPABILITY_LIMIT]
        return {
            "composite_path_available": self._cached_path is not None,
            "capability_count": len(self._last_capabilities),
            "capabilities": diagnostic_capabilities,
            "last_operation": (
                dict(self._last_operation)
                if self._last_operation is not None
                else None
            ),
        }

    def _path(self):
        # The composite object path is stable for the daemon's lifetime; discover it
        # once (a `busctl tree` spawn) and reuse — every method needs it, so this
        # roughly halves the busctl subprocesses per remap action.
        if self._cached_path is None:
            self._cached_path = _composite_path(self._run)
            if self._cached_path is None:
                self._discovery_failures += 1
                self._record(
                    "discover_composite",
                    False,
                    emit=self._is_logarithmic_sample(self._discovery_failures),
                    reason="composite_not_found",
                    failure_count=self._discovery_failures,
                )
            else:
                self._discovery_failures = 0
                self._record("discover_composite", True)
        return self._cached_path

    def _failed(self, r, operation) -> bool:
        """A busctl call failed → drop the cached path: the composite device may have
        been recreated (e.g. InputPlumber restart → CompositeDevice1), so the next
        call re-discovers it instead of hammering a dead object forever."""
        if not r or r.returncode != 0:
            details = (
                {"reason": "process_unavailable"}
                if r is None
                else {"reason": "busctl_exit", "returncode": int(r.returncode)}
            )
            self._cached_path = None
            self._last_capabilities = []
            self._last_reported_capabilities = None
            self._record(operation, False, **details)
            return True
        return False

    def capabilities(self) -> list:
        """The device's live capability strings (e.g. 'Gamepad:Button:RightPaddle1')."""
        path = self._path()
        if not path:
            return []
        r = self._run(["busctl", "get-property", SVC, path, IFACE, "Capabilities"])
        if self._failed(r, "read_capabilities"):
            return []
        # Output: as <n> "cap" "cap" ...  → pull the quoted strings.
        capabilities = re.findall(r'"([^"]+)"', r.stdout)
        self._last_capabilities = list(dict.fromkeys(capabilities))
        reported_capabilities = tuple(self._last_capabilities)
        changed = reported_capabilities != self._last_reported_capabilities
        self._record(
            "read_capabilities",
            True,
            emit=changed,
            capability_count=len(self._last_capabilities),
        )
        if changed:
            self._last_reported_capabilities = reported_capabilities
        return list(self._last_capabilities)

    def get_profile_yaml(self) -> str | None:
        path = self._path()
        if not path:
            return None
        r = self._run(["busctl", "--json=short", "call", SVC, path, IFACE, "GetProfileYaml"])
        if self._failed(r, "read_profile"):
            return None
        try:
            profile = json.loads(r.stdout)["data"][0]
            self._record("read_profile", True, profile_bytes=len(profile.encode()))
            return profile
        except Exception as exc:
            self._record(
                "read_profile",
                False,
                reason="invalid_response",
                error=type(exc).__name__,
            )
            return None

    def load_profile_yaml(self, yaml: str) -> bool:
        path = self._path()
        if not path:
            return False
        r = self._run(["busctl", "call", SVC, path, IFACE, "LoadProfileFromYaml", "s", yaml])
        if self._failed(r, "load_profile"):
            return False
        self._record("load_profile", True, profile_bytes=len(yaml.encode()))
        return True

    def reset_default(self) -> bool:
        path = self._path()
        if not path:
            return False
        r = self._run(["busctl", "call", SVC, path, IFACE, "LoadProfilePath", "s", DEFAULT_PROFILE_PATH])
        if self._failed(r, "reset_default"):
            return False
        self._record("reset_default", True)
        return True
