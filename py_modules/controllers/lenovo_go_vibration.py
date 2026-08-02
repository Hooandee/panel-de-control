"""Capability-gated hid-lenovo-go vibration controls for Legion Go 2."""

import glob
import os
import re
import time
from pathlib import Path


_INTENSITIES = ("off", "low", "medium", "high")
_PATTERNS = ("fps", "racing", "standard", "spg", "rpg")
_BOOLEANS = ("true", "false")
_GO2_PRODUCTS = {"61eb", "61ec", "61ed", "61ee"}
_READBACK_ATTEMPTS = 26
_READBACK_INTERVAL_S = 0.02


def _default_write_text(path, value):
    with open(path, "w") as output:
        output.write(value)


class LenovoGoVibrationAdapter:
    def __init__(
        self,
        device_key,
        source_paths,
        root="/",
        candidate_roots=None,
        write_text=None,
        sleep=None,
    ):
        self._device_key = device_key or ""
        self._source_paths = source_paths
        self._root = root
        self._candidate_roots = candidate_roots
        self._write_text = write_text or _default_write_text
        self._sleep = sleep or time.sleep
        self._last_operation = None
        self._last_probe = {"available": False, "reason": "not_probed"}

    def diagnostics(self):
        result = {"probe": dict(self._last_probe)}
        if self._last_operation:
            result.update(self._last_operation)
        return result

    def _path(self, absolute):
        return Path(self._root) / absolute.lstrip("/")

    @staticmethod
    def _usb_root(path):
        try:
            current = Path(path).resolve()
        except OSError:
            return None
        for candidate in (current, *current.parents):
            if (
                (candidate / "idVendor").is_file()
                and (candidate / "idProduct").is_file()
            ):
                return candidate
        return None

    @staticmethod
    def _usb_identity(path):
        usb = LenovoGoVibrationAdapter._usb_root(path)
        if usb is None:
            return None
        try:
            vendor = (usb / "idVendor").read_text().strip().lower()
            product = (usb / "idProduct").read_text().strip().lower()
        except OSError:
            return None
        return usb, vendor, product

    def _source_usb_roots(self):
        roots = set()
        try:
            sources = self._source_paths()
        except (OSError, TypeError, ValueError):
            return roots
        for source in sources:
            name = os.path.basename(source) if isinstance(source, str) else ""
            if not re.fullmatch(r"event\d+", name):
                continue
            usb = self._usb_root(
                self._path(f"/sys/class/input/{name}/device")
            )
            if usb is not None:
                roots.add(str(usb))
        return roots

    def _discover_candidates(self):
        if self._device_key != "legion_go_2":
            self._last_probe = {
                "available": False, "reason": "device_gate",
                "candidate_count": 0,
            }
            return []
        if self._candidate_roots is not None:
            try:
                candidates = [Path(path) for path in self._candidate_roots()]
                self._last_probe = {
                    "available": False,
                    "reason": "candidates_discovered",
                    "candidate_count": len(candidates),
                    "candidates": [path.name for path in candidates],
                }
                return candidates
            except (OSError, TypeError, ValueError):
                self._last_probe = {
                    "available": False, "reason": "candidate_probe_failed",
                    "candidate_count": 0,
                }
                return []
        source_usb_roots = self._source_usb_roots()
        if not source_usb_roots:
            self._last_probe = {
                "available": False, "reason": "source_usb_unavailable",
                "candidate_count": 0,
            }
            return []
        paths = glob.glob(str(self._path(
            "/sys/bus/hid/drivers/hid-lenovo-go/*/rumble_intensity"
        )))
        candidates = []
        for intensity_path in paths:
            candidate = Path(intensity_path).parent
            identity = self._usb_identity(candidate)
            if identity is None:
                continue
            usb, vendor, product = identity
            if (
                vendor == "17ef"
                and product in _GO2_PRODUCTS
                and str(usb) in source_usb_roots
            ):
                candidates.append(candidate)
        self._last_probe = {
            "available": False,
            "reason": "candidates_discovered",
            "candidate_count": len(candidates),
            "candidates": [path.name for path in candidates],
        }
        return candidates

    @staticmethod
    def _read(path):
        try:
            return path.read_text().strip()
        except OSError:
            return None

    def _wait_for(self, path, expected):
        for attempt in range(_READBACK_ATTEMPTS):
            if self._read(path) == expected:
                return True
            if attempt + 1 < _READBACK_ATTEMPTS:
                self._sleep(_READBACK_INTERVAL_S)
        return False

    def _read_options(self, path, expected):
        values = (self._read(path) or "").split()
        if len(values) != len(set(values)) or set(values) != set(expected):
            return None
        return [value for value in expected if value in values]

    def _surface(self):
        candidates = self._discover_candidates()
        if len(candidates) != 1:
            self._last_probe["reason"] = (
                "ambiguous" if len(candidates) > 1 else "not_found"
            )
            return None
        root = candidates[0]
        options = {
            "intensity_options": self._read_options(
                root / "rumble_intensity_index", _INTENSITIES
            ),
            "left_pattern_options": self._read_options(
                root / "left_handle/rumble_mode_index", _PATTERNS
            ),
            "right_pattern_options": self._read_options(
                root / "right_handle/rumble_mode_index", _PATTERNS
            ),
            "touchpad_enabled_options": self._read_options(
                root / "touchpad/vibration_enabled_index", _BOOLEANS
            ),
            "touchpad_intensity_options": self._read_options(
                root / "touchpad/vibration_intensity_index", _INTENSITIES
            ),
        }
        if any(value is None for value in options.values()):
            self._last_probe.update({
                "available": False,
                "reason": "incomplete_surface",
                "missing_indexes": sorted(
                    key for key, value in options.items() if value is None
                ),
            })
            return None
        raw = {
            "intensity": self._read(root / "rumble_intensity"),
            "left_pattern": self._read(root / "left_handle/rumble_mode"),
            "right_pattern": self._read(root / "right_handle/rumble_mode"),
            "touchpad_enabled": self._read(
                root / "touchpad/vibration_enabled"
            ),
            "touchpad_intensity": self._read(
                root / "touchpad/vibration_intensity"
            ),
        }
        raw_options = {
            "intensity": options["intensity_options"],
            "left_pattern": options["left_pattern_options"],
            "right_pattern": options["right_pattern_options"],
            "touchpad_enabled": options["touchpad_enabled_options"],
            "touchpad_intensity": options["touchpad_intensity_options"],
        }
        if any(
            value != "unknown" and value not in raw_options[field]
            for field, value in raw.items()
        ):
            self._last_probe.update({
                "available": False,
                "reason": "invalid_readback",
            })
            return None
        unknown = [value == "unknown" for value in raw.values()]
        if any(unknown) and not all(unknown):
            self._last_probe.update({
                "available": False,
                "reason": "mixed_readback",
            })
            return None
        readable = all(
            value in raw_options[field]
            for field, value in raw.items()
        )
        self._last_probe.update({
            "available": True,
            "reason": (
                "available" if readable else "available_without_readback"
            ),
        })
        return root, options, raw if readable else None

    def state(self):
        surface = self._surface()
        if surface is None:
            return None
        _, _, raw = surface
        if raw is None:
            return None
        return {
            "intensity": raw["intensity"],
            "left_pattern": raw["left_pattern"],
            "right_pattern": raw["right_pattern"],
            "touchpad_enabled": raw["touchpad_enabled"] == "true",
            "touchpad_intensity": raw["touchpad_intensity"],
        }

    def capabilities(self):
        surface = self._surface()
        if surface is None:
            return None
        _, options, raw = surface
        return {
            "intensity_options": options["intensity_options"],
            "left_pattern_options": options["left_pattern_options"],
            "right_pattern_options": options["right_pattern_options"],
            "touchpad_enabled_options": [
                value == "true"
                for value in options["touchpad_enabled_options"]
            ],
            "touchpad_intensity_options": options[
                "touchpad_intensity_options"
            ],
            "readback": "driver" if raw is not None else "none",
        }

    def apply(self, patch):
        surface = self._surface()
        if surface is None or not isinstance(patch, dict):
            self._last_operation = {
                "mode": "lenovo_hd",
                "ok": False,
                "reason": "unsupported",
            }
            return False
        root, options, raw = surface
        raw = raw or {}
        desired = {
            "intensity": patch.get("intensity", raw.get("intensity")),
            "left_pattern": patch.get(
                "left_pattern", patch.get("pattern", raw.get("left_pattern"))
            ),
            "right_pattern": patch.get(
                "right_pattern", patch.get("pattern", raw.get("right_pattern"))
            ),
            "touchpad_enabled": patch.get(
                "touchpad_enabled",
                (
                    raw.get("touchpad_enabled") == "true"
                    if "touchpad_enabled" in raw else None
                ),
            ),
            "touchpad_intensity": patch.get(
                "touchpad_intensity", raw.get("touchpad_intensity")
            ),
        }
        if (
            desired["intensity"] not in options["intensity_options"]
            or desired["left_pattern"] not in options["left_pattern_options"]
            or desired["right_pattern"] not in options["right_pattern_options"]
            or not isinstance(desired["touchpad_enabled"], bool)
            or desired["touchpad_intensity"]
            not in options["touchpad_intensity_options"]
        ):
            self._last_operation = {
                "mode": "lenovo_hd",
                "ok": False,
                "reason": "invalid_value",
            }
            return False
        writes = (
            (root / "rumble_intensity", desired["intensity"], raw.get("intensity")),
            (
                root / "left_handle/rumble_mode",
                desired["left_pattern"],
                raw.get("left_pattern"),
            ),
            (
                root / "right_handle/rumble_mode",
                desired["right_pattern"],
                raw.get("right_pattern"),
            ),
            (
                root / "touchpad/vibration_enabled",
                "true" if desired["touchpad_enabled"] else "false",
                raw.get("touchpad_enabled"),
            ),
            (
                root / "touchpad/vibration_intensity",
                desired["touchpad_intensity"],
                raw.get("touchpad_intensity"),
            ),
        )
        changed = []
        reason = "write_failed"
        readable = bool(raw)
        try:
            for path, value, baseline in writes:
                self._write_text(path, value)
                changed.append((path, baseline))
                if readable and not self._wait_for(path, value):
                    reason = "readback_mismatch"
                    raise OSError("driver readback mismatch")
        except OSError:
            rollback_confirmed = True
            for path, baseline in reversed(changed):
                if baseline is None:
                    rollback_confirmed = False
                    continue
                try:
                    self._write_text(path, baseline)
                    rollback_confirmed &= self._wait_for(path, baseline)
                except OSError:
                    rollback_confirmed = False
            self._last_operation = {
                "mode": "lenovo_hd",
                "ok": False,
                "reason": reason,
                "rollback_confirmed": rollback_confirmed,
            }
            return False
        self._last_operation = {
            "mode": "lenovo_hd",
            "ok": True,
            "readback": readable,
            "confirmation": "driver" if readable else "accepted",
        }
        return True
