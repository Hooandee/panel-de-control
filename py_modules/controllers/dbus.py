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
FF_IFACE = "org.shadowblip.Output.ForceFeedback"
MANAGER_PATH = "/org/shadowblip/InputPlumber/Manager"
MANAGER_IFACE = "org.shadowblip.InputManager"
TARGET_IFACE = "org.shadowblip.Input.Target"
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


def _composite_paths(run) -> list[str]:
    r = run(["busctl", "tree", SVC])
    if not r or r.returncode != 0:
        return []
    return list(dict.fromkeys(
        re.findall(r"(/org/shadowblip/InputPlumber/CompositeDevice\d+)", r.stdout)
    ))


class IpDbus:
    """Drives the active CompositeDevice: read capabilities + current profile,
    load a remap profile, reset to default."""

    def __init__(self, run=_run, event_cb=None, expected_names=()):
        self._run = run
        self._event_cb = event_cb
        self._expected_names = tuple(expected_names or ())
        self._cached_path = None
        self._composite_name = None
        self._source_device_count = None
        self._last_capabilities = []
        self._last_reported_capabilities = None
        self._discovery_failures = 0
        self._last_operation = None
        self._profile_apply = None

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
        result = {
            "composite_path_available": self._cached_path is not None,
            "capability_count": len(self._last_capabilities),
            "capabilities": diagnostic_capabilities,
            "last_operation": (
                dict(self._last_operation)
                if self._last_operation is not None
                else None
            ),
        }
        if self._composite_name is not None:
            result["composite_name"] = self._composite_name
            result["source_device_count"] = self._source_device_count
        if self._profile_apply is not None:
            result["profile_apply"] = dict(self._profile_apply)
        return result

    def record_profile_apply(self, ok, reason=None, **details):
        self._profile_apply = {
            "ok": bool(ok),
            **({} if reason is None else {"reason": reason}),
            **details,
        }
        self._record(
            "apply_profile", ok,
            **({} if reason is None else {"reason": reason}),
            **details,
        )

    def profile_apply_status(self):
        return (
            dict(self._profile_apply)
            if self._profile_apply is not None
            else None
        )

    def set_expected_names(self, names) -> None:
        names = tuple(names or ())
        if names != self._expected_names:
            self._expected_names = names
            self._cached_path = None
            self._composite_name = None
            self._source_device_count = None

    def _read_property(self, path, interface, prop):
        return self._run(["busctl", "get-property", SVC, path, interface, prop])

    def _clear_cached_path(self):
        self._cached_path = None
        self._composite_name = None
        self._source_device_count = None
        self._last_capabilities = []
        self._last_reported_capabilities = None

    def _discover_composite(self):
        paths = _composite_paths(self._run)
        if not paths:
            return None, "composite_not_found"
        if not self._expected_names:
            if len(paths) != 1:
                return None, "composite_ambiguous"
            return paths[0], None

        matches = []
        for path in paths:
            name_result = self._read_property(path, IFACE, "Name")
            sources_result = self._read_property(path, IFACE, "SourceDevicePaths")
            if (
                not name_result
                or name_result.returncode != 0
                or not sources_result
                or sources_result.returncode != 0
            ):
                continue
            names = re.findall(r'"([^"]+)"', name_result.stdout)
            sources = [
                source for source in re.findall(r'"([^"]*)"', sources_result.stdout)
                if source
            ]
            if names and names[0] in self._expected_names and sources:
                matches.append((path, names[0], len(sources)))
        if len(matches) != 1:
            return None, (
                "composite_not_found" if not matches else "composite_ambiguous"
            )
        path, self._composite_name, self._source_device_count = matches[0]
        return path, None

    def _cached_identity_valid(self) -> bool:
        if self._cached_path is None or not self._expected_names:
            return self._cached_path is not None
        name_result = self._read_property(
            self._cached_path, IFACE, "Name"
        )
        sources_result = self._read_property(
            self._cached_path, IFACE, "SourceDevicePaths"
        )
        if (
            not name_result
            or name_result.returncode != 0
            or not sources_result
            or sources_result.returncode != 0
        ):
            self._clear_cached_path()
            self._record(
                "validate_composite", False,
                reason="identity_unavailable",
            )
            return False
        names = re.findall(r'"([^"]+)"', name_result.stdout)
        sources = [
            value for value in re.findall(
                r'"([^"]*)"', sources_result.stdout
            )
            if value
        ]
        if (
            not names
            or names[0] not in self._expected_names
            or not sources
        ):
            self._clear_cached_path()
            self._record(
                "validate_composite", False, reason="identity_changed"
            )
            return False
        self._composite_name = names[0]
        self._source_device_count = len(sources)
        return True

    def _path(self, revalidate=False):
        # The composite object path is stable for the daemon's lifetime; discover it
        # once (a `busctl tree` spawn) and reuse — every method needs it, so this
        # roughly halves the busctl subprocesses per remap action.
        if self._cached_path is None:
            self._cached_path, reason = self._discover_composite()
            if self._cached_path is None:
                self._discovery_failures += 1
                self._record(
                    "discover_composite",
                    False,
                    emit=self._is_logarithmic_sample(self._discovery_failures),
                    reason=reason,
                    failure_count=self._discovery_failures,
                )
            else:
                self._discovery_failures = 0
                self._record("discover_composite", True)
        if revalidate and not self._cached_identity_valid():
            return None
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
            self._clear_cached_path()
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

    def source_device_paths(self) -> list:
        path = self._path(revalidate=True)
        if not path:
            return []
        r = self._read_property(path, IFACE, "SourceDevicePaths")
        if self._failed(r, "read_source_device_paths"):
            return []
        paths = [
            value for value in re.findall(r'"([^"]*)"', r.stdout)
            if value
        ]
        self._record(
            "read_source_device_paths", True, source_device_count=len(paths)
        )
        return paths

    def supported_target_device_ids(self) -> list:
        r = self._read_property(
            MANAGER_PATH, MANAGER_IFACE, "SupportedTargetDeviceIds"
        )
        if not r or r.returncode != 0:
            self._record(
                "read_supported_target_device_ids", False,
                reason=(
                    "process_unavailable" if r is None else "busctl_exit"
                ),
            )
            return []
        ids = re.findall(r'"([^"]+)"', r.stdout)
        self._record(
            "read_supported_target_device_ids", True,
            target_type_count=len(ids),
        )
        return list(dict.fromkeys(ids))

    def target_device_types(self) -> list:
        path = self._path(revalidate=True)
        if not path:
            return []
        result = self._read_property(path, IFACE, "TargetDevices")
        if self._failed(result, "read_target_devices"):
            return []
        paths = [
            value for value in re.findall(r'"([^"]*)"', result.stdout)
            if value
        ]
        if not paths:
            self._record(
                "read_target_device_types", False,
                reason="target_devices_empty",
            )
            return []
        types = []
        for target_path in paths:
            target = self._read_property(
                target_path, TARGET_IFACE, "DeviceType"
            )
            if not target or target.returncode != 0:
                self._record(
                    "read_target_device_types", False,
                    reason="target_identity_unavailable",
                )
                return []
            values = re.findall(r'"([^"]+)"', target.stdout)
            if len(values) != 1:
                self._record(
                    "read_target_device_types", False,
                    reason="target_identity_invalid",
                )
                return []
            types.append(values[0])
        self._record(
            "read_target_device_types", True,
            target_type_count=len(types),
        )
        return types

    def set_target_devices(self, target_types) -> bool:
        path = self._path(revalidate=True)
        if not path or not isinstance(target_types, list):
            return False
        r = self._run([
            "busctl", "call", SVC, path, IFACE, "SetTargetDevices", "as",
            str(len(target_types)), *target_types,
        ])
        if self._failed(r, "set_target_devices"):
            return False
        self._record(
            "set_target_devices", True,
            target_type_count=len(target_types),
        )
        return True

    def get_profile_yaml(self) -> str | None:
        path = self._path(revalidate=True)
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
        path = self._path(revalidate=True)
        if not path:
            return False
        r = self._run(["busctl", "call", SVC, path, IFACE, "LoadProfileFromYaml", "s", yaml])
        if self._failed(r, "load_profile"):
            return False
        self._record("load_profile", True, profile_bytes=len(yaml.encode()))
        return True

    def reset_default(self) -> bool:
        path = self._path(revalidate=True)
        if not path:
            return False
        r = self._run(["busctl", "call", SVC, path, IFACE, "LoadProfilePath", "s", DEFAULT_PROFILE_PATH])
        if self._failed(r, "reset_default"):
            return False
        self._record("reset_default", True)
        return True

    def force_feedback_enabled(self):
        path = self._path(revalidate=True)
        if not path:
            return None
        r = self._read_property(path, FF_IFACE, "Enabled")
        if self._failed(r, "read_force_feedback"):
            return None
        match = re.search(r"\b(true|false)\b", r.stdout)
        if not match:
            self._record(
                "read_force_feedback", False, reason="invalid_response"
            )
            return None
        enabled = match.group(1) == "true"
        self._record("read_force_feedback", True, enabled=enabled)
        return enabled

    def set_force_feedback_enabled(self, enabled: bool) -> bool:
        path = self._path(revalidate=True)
        if not path:
            return False
        desired = bool(enabled)
        r = self._run([
            "busctl", "set-property", SVC, path, FF_IFACE, "Enabled", "b",
            "true" if desired else "false",
        ])
        if self._failed(r, "set_force_feedback"):
            return False
        actual = self.force_feedback_enabled()
        ok = actual is desired
        self._record(
            "set_force_feedback",
            ok,
            desired=desired,
            actual=actual,
            **({} if ok else {"reason": "readback_mismatch"}),
        )
        return ok

    def rumble(self, strength) -> bool:
        path = self._path(revalidate=True)
        if not path:
            return False
        try:
            value = min(1.0, max(0.0, float(strength)))
        except (TypeError, ValueError):
            return False
        r = self._run([
            "busctl", "call", SVC, path, FF_IFACE, "Rumble", "d",
            f"{value:g}",
        ])
        if self._failed(r, "rumble"):
            return False
        self._record("rumble", True, strength=value)
        return True

    def stop_rumble(self) -> bool:
        path = self._path(revalidate=True)
        if not path:
            return False
        r = self._run(["busctl", "call", SVC, path, FF_IFACE, "Stop"])
        if self._failed(r, "stop_rumble"):
            return False
        self._record("stop_rumble", True)
        return True
