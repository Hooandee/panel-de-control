"""Persistent per-game vibration controls exposed by the active kernel stack.

InputPlumber owns routing and transient test effects. Persistent intensity uses
the narrowest device interface available: ASUS' two-motor sysfs control with
readback, otherwise the selected physical evdev source's FF_GAIN. The desired
value is stored by RemapStore and re-applied on game changes.
"""
import ctypes
import glob
import math
import os
import re
import struct
import time

from controllers.asus_xbox_haptics import AsusXboxHapticsAdapter
from controllers.lenovo_go_vibration import LenovoGoVibrationAdapter


_LENOVO_DEFAULT_STATE = {
    "intensity": "medium",
    "left_pattern": "fps",
    "right_pattern": "fps",
    "touchpad_enabled": True,
    "touchpad_intensity": "medium",
}

try:
    import fcntl
except ImportError:  # Windows imports the shared backend but has no evdev/ioctl.
    fcntl = None

_EV_FF = 0x15
_FF_RUMBLE = 0x50
_FF_GAIN = 0x60
_ASUS_KEYS = {"rog_ally"}
_GAIN_KEYS = {"legion_go", "legion_go_s", "legion_go_2"}
_ASUS_NATIVE_MAX = 64


class _FFTrigger(ctypes.Structure):
    _fields_ = [("button", ctypes.c_uint16), ("interval", ctypes.c_uint16)]


class _FFReplay(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint16), ("delay", ctypes.c_uint16)]


class _FFRumble(ctypes.Structure):
    _fields_ = [
        ("strong_magnitude", ctypes.c_uint16),
        ("weak_magnitude", ctypes.c_uint16),
    ]


class _FFEffectUnion(ctypes.Union):
    _fields_ = [
        ("rumble", _FFRumble),
        ("_storage", ctypes.c_uint8 * 32),
        ("_alignment", ctypes.c_void_p),
    ]


class _FFEffect(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint16),
        ("id", ctypes.c_int16),
        ("direction", ctypes.c_uint16),
        ("trigger", _FFTrigger),
        ("replay", _FFReplay),
        ("u", _FFEffectUnion),
    ]


def _iow(event_type, number, size):
    return (1 << 30) | (size << 16) | (event_type << 8) | number


_EVIOCSFF = _iow(ord("E"), 0x80, ctypes.sizeof(_FFEffect))
_EVIOCRMFF = _iow(ord("E"), 0x81, ctypes.sizeof(ctypes.c_int))


def _default_write_text(path, value):
    with open(path, "w") as f:
        f.write(value)


def _ff_bits(raw):
    try:
        words = [int(word, 16) for word in raw.split()]
    except (TypeError, ValueError):
        return 0
    bits = 0
    for index, word in enumerate(reversed(words)):
        bits |= word << (index * 64)
    return bits


class VibrationController:
    def __init__(self, device_key, dbus, root="/", write_text=None,
                 open_device=None, write_event=None, ioctl=None,
                 close_device=None, sleep=None, lenovo_adapter=None,
                 lenovo_baseline=None, lenovo_route=False,
                 xbox_adapter=None):
        self._device_key = device_key or ""
        self._dbus = dbus
        self._root = root
        self._write_text = write_text or _default_write_text
        self._open_device = open_device or os.open
        self._write_event = write_event or os.write
        self._ioctl = ioctl or getattr(fcntl, "ioctl", None)
        self._close_device = close_device or os.close
        self._sleep = sleep or time.sleep
        self._last_operation = None
        self._xbox = xbox_adapter or AsusXboxHapticsAdapter(
            self._device_key,
            root=self._root,
            write_text=self._write_text,
            sleep=self._sleep,
            dbus=self._dbus,
        )
        self._lenovo = lenovo_adapter or LenovoGoVibrationAdapter(
            self._device_key,
            getattr(self._dbus, "source_device_paths", lambda: []),
            root=self._root,
            write_text=self._write_text,
        )
        native_fields = (
            "intensity", "left_pattern", "right_pattern",
            "touchpad_enabled", "touchpad_intensity",
        )
        baseline = lenovo_baseline if isinstance(lenovo_baseline, dict) else {}
        complete_baseline = all(field in baseline for field in native_fields)
        self._lenovo_owned = (
            self._device_key == "legion_go_2"
            and (bool(lenovo_route) or complete_baseline)
        )
        self._lenovo_last_state = (
            {
                **_LENOVO_DEFAULT_STATE,
                **{
                    field: baseline[field]
                    for field in native_fields if field in baseline
                },
            }
            if self._lenovo_owned else None
        )
        self._lenovo_last_capabilities = None

    def _probe_lenovo(self):
        snapshot = getattr(self._lenovo, "snapshot", lambda: None)()
        if snapshot is None:
            current = self._lenovo.state()
            capabilities = self._lenovo.capabilities()
        else:
            current = snapshot.get("state")
            capabilities = snapshot.get("capabilities")
        return current, capabilities

    def diagnostics(self):
        result = (
            dict(self._last_operation)
            if self._last_operation is not None
            else {}
        )
        if self._device_key == "legion_go_2":
            native_diagnostics = getattr(
                self._lenovo, "diagnostics", lambda: None
            )()
            if native_diagnostics is not None:
                result["lenovo_hd"] = native_diagnostics
        if self._device_key == "rog_xbox_ally_x":
            native_diagnostics = getattr(
                self._xbox, "diagnostics", lambda: None
            )()
            if native_diagnostics is not None:
                result["asus_xbox_hd"] = native_diagnostics
        return result or None

    def _xbox_state(self):
        if self._device_key != "rog_xbox_ally_x":
            return None
        return self._xbox.state()

    def _path(self, absolute):
        return os.path.join(self._root, absolute.lstrip("/"))

    def _asus_path(self):
        if self._device_key not in _ASUS_KEYS:
            return None
        matches = glob.glob(self._path(
            "/sys/bus/hid/drivers/asus_rog_ally/*/vibration_intensity"
        ))
        return matches[0] if len(matches) == 1 else None

    def _lenovo_state(self, probe=None):
        if self._device_key != "legion_go_2":
            return None
        current, capabilities = probe or self._probe_lenovo()
        if current is not None:
            self._lenovo_owned = True
            self._lenovo_last_state = dict(current)
            if capabilities is not None:
                self._lenovo_last_capabilities = dict(capabilities)
            return {
                **current,
                "readback": True,
                "connected": True,
            }
        if capabilities is not None:
            self._lenovo_owned = True
            self._lenovo_last_capabilities = dict(capabilities)
            if self._lenovo_last_state is None:
                self._lenovo_last_state = dict(_LENOVO_DEFAULT_STATE)
            return {
                **self._lenovo_last_state,
                "readback": False,
                "connected": True,
            }
        if self._lenovo_owned and self._lenovo_last_state is not None:
            return {
                **self._lenovo_last_state,
                "readback": False,
                "connected": False,
            }
        return None

    def _lenovo_capabilities(self, state):
        if state is None or state.get("mode") != "lenovo_hd":
            return None
        native = self._lenovo_last_capabilities or {}
        return {
            "mode": "lenovo_hd",
            "channels": ["handles", "touchpad"],
            **native,
            "readback": (
                native.get("readback", "none")
                if state["connected"] else "none"
            ),
            "test": {
                "patterns": ["pulse"],
                "channels": ["strong", "weak", "both"],
            },
        }

    def snapshot(self):
        if self._device_key == "rog_xbox_ally_x":
            snapshot = getattr(self._xbox, "snapshot", lambda: None)()
            if isinstance(snapshot, dict):
                return snapshot
        if self._device_key == "legion_go_2":
            lenovo = self._lenovo_state(self._probe_lenovo())
            if lenovo is None:
                state = self.state()
                return {
                    "state": state,
                    "capabilities": self.capabilities(state),
                }
            state = {"mode": "lenovo_hd", "persistent": True, **lenovo}
            return {
                "state": state,
                "capabilities": self._lenovo_capabilities(state),
            }
        state = self.state()
        return {"state": state, "capabilities": self.capabilities(state)}

    @staticmethod
    def _read_dual_native(path):
        try:
            with open(path) as f:
                values = [int(value) for value in f.read().split()]
        except (OSError, ValueError):
            return None
        if len(values) != 2 or any(
            value < 0 or value > _ASUS_NATIVE_MAX for value in values
        ):
            return None
        return values[0], values[1]

    @staticmethod
    def _native_percent(value):
        bounded = min(_ASUS_NATIVE_MAX, max(0, value))
        return min(100, round((bounded * 100 / _ASUS_NATIVE_MAX) / 5) * 5)

    @staticmethod
    def _native_value(percent):
        return round(percent * _ASUS_NATIVE_MAX / 100)

    def _gain_path(self):
        if self._device_key not in _GAIN_KEYS:
            return None
        source_paths = getattr(self._dbus, "source_device_paths", lambda: [])()
        matches = []
        for source in source_paths:
            name = os.path.basename(source)
            if not re.fullmatch(r"event\d+", name):
                continue
            capability_path = self._path(
                f"/sys/class/input/{name}/device/capabilities/ff"
            )
            try:
                with open(capability_path) as f:
                    bits = _ff_bits(f.read())
            except OSError:
                continue
            if bits & (1 << _FF_GAIN) and bits & (1 << _FF_RUMBLE):
                matches.append(self._path(source))
        return matches[0] if len(matches) == 1 else None

    def state(self):
        xbox = self._xbox_state()
        if xbox is not None:
            return xbox
        lenovo = self._lenovo_state()
        if lenovo is not None:
            return {
                "mode": "lenovo_hd",
                "persistent": True,
                **lenovo,
            }
        asus_path = self._asus_path()
        if asus_path is not None:
            values = self._read_dual_native(asus_path)
            if values is None:
                return None
            left, right = (
                self._native_percent(value) for value in values
            )
            return {
                "mode": "dual",
                "persistent": True,
                "left": left,
                "right": right,
                "min": 0,
                "max": 100,
                "step": 5,
                "readback": True,
            }
        if self._gain_path() is not None:
            return {
                "mode": "gain",
                "persistent": True,
                "value": None,
                "min": 0,
                "max": 100,
                "step": 5,
                "readback": False,
            }
        return None

    def capabilities(self, state=None):
        if state is None:
            state = self.state()
        if state is not None and state["mode"] == "asus_xbox_hd":
            return self._xbox.capabilities(state)
        if state is not None and state["mode"] == "lenovo_hd":
            return self._lenovo_capabilities(state)
        if state is not None and state["mode"] == "dual":
            return {
                "mode": "dual",
                "channels": ["left", "right"],
                "readback": "driver",
                "min": 0,
                "max": 100,
                "step": 5,
                "test": {
                    "patterns": ["pulse"],
                    "channels": ["left", "right", "both"],
                },
            }
        if state is not None and state["mode"] == "gain":
            return {
                "mode": "gain",
                "channels": [],
                "readback": "none",
                "min": 0,
                "max": 100,
                "step": 5,
                "test": {
                    "patterns": ["pulse"],
                    "channels": ["strong", "weak", "both"],
                },
            }
        try:
            enabled = self._dbus.force_feedback_enabled()
        except (AttributeError, OSError, TypeError, ValueError):
            enabled = None
        if isinstance(enabled, bool):
            return {
                "mode": "enabled_only",
                "channels": [],
                "readback": "none",
                "test": {
                    "patterns": ["pulse"],
                    "channels": ["both"],
                },
            }
        return {
            "mode": "unavailable",
            "channels": [],
            "readback": "none",
            "test": {"patterns": [], "channels": []},
        }

    def capture_baseline(self):
        if self._xbox_state() is not None:
            return self._xbox.capture_baseline()
        lenovo = self._lenovo_state()
        if (
            lenovo is not None
            and lenovo["connected"]
            and lenovo["readback"]
        ):
            return {
                field: lenovo[field]
                for field in (
                    "intensity", "left_pattern", "right_pattern", "touchpad_enabled",
                    "touchpad_intensity",
                )
            }
        asus_path = self._asus_path()
        if asus_path is None:
            return {}
        values = self._read_dual_native(asus_path)
        if values is None:
            return {}
        return {
            "native_left": values[0],
            "native_right": values[1],
        }

    @staticmethod
    def _percent(value):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            return None
        return min(100, max(0, round(float(value) / 5) * 5))

    def _apply_dual_native(self, path, desired_native):
        current = self._read_dual_native(path)
        if current is None:
            self._last_operation = {
                "mode": "dual", "ok": False,
                "reason": "initial_readback_unavailable",
            }
            return False
        desired = f"{desired_native[0]} {desired_native[1]}\n"
        try:
            self._write_text(path, desired)
        except OSError:
            self._last_operation = {
                "mode": "dual", "ok": False, "reason": "write_failed",
            }
            return False
        if self._read_dual_native(path) == desired_native:
            self._last_operation = {
                "mode": "dual", "ok": True, "readback": True,
            }
            return True
        rollback_confirmed = False
        rollback = current
        try:
            self._write_text(path, f"{rollback[0]} {rollback[1]}\n")
            rollback_confirmed = self._read_dual_native(path) == rollback
        except OSError:
            pass
        self._last_operation = {
            "mode": "dual",
            "ok": False,
            "reason": "readback_mismatch",
            "rollback_confirmed": rollback_confirmed,
        }
        return False

    def _apply_dual(self, path, patch):
        if self._read_dual_native(path) is None:
            self._last_operation = {
                "mode": "dual", "ok": False,
                "reason": "initial_readback_unavailable",
            }
            return False
        left = self._percent(patch.get("left"))
        right = self._percent(patch.get("right"))
        if left is None or right is None:
            self._last_operation = {
                "mode": "dual", "ok": False, "reason": "invalid_value",
            }
            return False
        desired_native = (
            self._native_value(left), self._native_value(right)
        )
        return self._apply_dual_native(path, desired_native)

    def restore_baseline(self, baseline):
        if not isinstance(baseline, dict):
            return False
        if self._xbox_state() is not None:
            restored = self._xbox.restore_baseline(baseline)
            self._last_operation = self._xbox.diagnostics()
            return restored
        if self._lenovo_owned and all(
            field in baseline
            for field in (
                "intensity", "left_pattern", "right_pattern", "touchpad_enabled",
                "touchpad_intensity",
            )
        ):
            restored = self._lenovo.apply(baseline)
            self._last_operation = self._lenovo.diagnostics()
            return restored
        asus_path = self._asus_path()
        native = (
            baseline.get("native_left"), baseline.get("native_right")
        )
        if asus_path is not None and all(
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value <= _ASUS_NATIVE_MAX
            for value in native
        ):
            return self._apply_dual_native(asus_path, native)
        return self.apply(baseline)

    def _write_native_exact(self, path, values):
        try:
            self._write_text(path, f"{values[0]} {values[1]}\n")
        except OSError:
            return False
        return self._read_dual_native(path) == values

    @staticmethod
    def _test_result(sent, stopped, restored, reason):
        return {
            "sent": sent,
            "stopped": stopped,
            "restored": restored,
            "reason": reason,
        }

    def _test_gain_channel(self, path, channel, strength):
        if self._ioctl is None:
            return self._test_result(
                False, False, True, "start_failed"
            )
        magnitude = round(strength * 0xFFFF / 100)
        effect = _FFEffect(
            type=_FF_RUMBLE,
            id=-1,
            replay=_FFReplay(length=180, delay=0),
        )
        effect.u.rumble = _FFRumble(
            strong_magnitude=(
                magnitude if channel in {"strong", "both"} else 0
            ),
            weak_magnitude=(
                magnitude if channel in {"weak", "both"} else 0
            ),
        )
        buffer = bytearray(bytes(effect))
        fd = None
        effect_id = None
        sent = False
        stopped = False
        restored = True
        try:
            fd = self._open_device(
                path, os.O_RDWR | os.O_NONBLOCK
            )
            self._ioctl(fd, _EVIOCSFF, buffer, True)
            effect_id = _FFEffect.from_buffer(buffer).id
            if effect_id < 0:
                raise OSError("force-feedback upload returned no id")
            play = struct.pack(
                "llHHi", 0, 0, _EV_FF, effect_id, 1
            )
            sent = self._write_event(fd, play) == len(play)
            if sent:
                self._sleep(0.18)
        except (OSError, TypeError, ValueError):
            sent = False
        finally:
            if fd is not None and effect_id is not None:
                stop = struct.pack(
                    "llHHi", 0, 0, _EV_FF, effect_id, 0
                )
                try:
                    stopped = self._write_event(fd, stop) == len(stop)
                except OSError:
                    stopped = False
                try:
                    self._ioctl(fd, _EVIOCRMFF, effect_id)
                except OSError:
                    restored = False
            if fd is not None:
                self._close_device(fd)

        if not restored:
            reason = "restore_failed"
        elif not stopped:
            reason = "stop_failed" if sent else "start_failed"
        elif not sent:
            reason = "start_failed"
        else:
            reason = None
        result = self._test_result(sent, stopped, restored, reason)
        self._last_operation = {
            "mode": "gain", "ok": reason is None, "test": result,
        }
        return result

    def test(self, pattern, channel, strength):
        if pattern != "pulse":
            return self._test_result(
                False, False, True, "unsupported_pattern"
            )
        if (
            not isinstance(strength, int)
            or isinstance(strength, bool)
            or not 0 <= strength <= 100
        ):
            return self._test_result(
                False, False, True, "invalid_strength"
            )

        capabilities = self.capabilities()
        channels = capabilities["test"]["channels"]
        selected_channel = "both" if channel is None else channel
        if selected_channel not in channels:
            return self._test_result(
                False, False, True, "unsupported_channel"
            )

        if capabilities["mode"] == "asus_xbox_hd":
            result = self._xbox.test(
                pattern, selected_channel, strength
            )
            self._last_operation = self._xbox.diagnostics()
            return result

        if capabilities["mode"] in {"gain", "lenovo_hd"}:
            path = self._gain_path()
            if path is None:
                return self._test_result(
                    False, False, True, "start_failed"
                )
            return self._test_gain_channel(
                path, selected_channel, strength
            )

        native_path = self._asus_path()
        native_baseline = None
        prepared = True
        if capabilities["mode"] == "dual":
            native_baseline = (
                self._read_dual_native(native_path)
                if native_path is not None else None
            )
            native_strength = self._native_value(strength)
            requested = {
                "left": (native_strength, 0),
                "right": (0, native_strength),
                "both": (native_strength, native_strength),
            }[selected_channel]
            prepared = (
                native_baseline is not None
                and native_path is not None
                and self._write_native_exact(native_path, requested)
            )

        sent = False
        stopped = False
        restored = True
        try:
            if prepared:
                rumble_strength = (
                    1.0
                    if capabilities["mode"] == "dual"
                    else strength / 100
                )
                try:
                    sent = bool(self._dbus.rumble(rumble_strength))
                    if sent:
                        self._sleep(0.18)
                except (AttributeError, OSError, TypeError, ValueError):
                    sent = False
        finally:
            try:
                stopped = bool(self._dbus.stop_rumble())
            except (AttributeError, OSError, TypeError, ValueError):
                stopped = False
            if native_baseline is not None and native_path is not None:
                restored = self._write_native_exact(
                    native_path, native_baseline
                )

        if not restored:
            reason = "restore_failed"
        elif not stopped:
            reason = "stop_failed"
        elif not prepared or not sent:
            reason = "start_failed"
        else:
            reason = None
        self._last_operation = {
            "mode": capabilities["mode"],
            "ok": reason is None,
            "test": self._test_result(sent, stopped, restored, reason),
        }
        return self._test_result(sent, stopped, restored, reason)

    def _apply_gain(self, path, value):
        amount = VibrationController._percent(value)
        if amount is None:
            self._last_operation = {
                "mode": "gain", "ok": False, "reason": "invalid_value",
            }
            return False
        event = struct.pack(
            "llHHi", 0, 0, _EV_FF, _FF_GAIN,
            round(amount * 0xFFFF / 100),
        )
        fd = None
        try:
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
            accepted = os.write(fd, event) == len(event)
            self._last_operation = {
                "mode": "gain",
                "ok": accepted,
                "readback": False,
                **({} if accepted else {"reason": "short_write"}),
            }
            return accepted
        except OSError:
            self._last_operation = {
                "mode": "gain", "ok": False, "reason": "write_failed",
                "readback": False,
            }
            return False
        finally:
            if fd is not None:
                os.close(fd)

    def apply_gain(self, value):
        path = self._gain_path()
        if path is None:
            self._last_operation = {
                "mode": "gain", "ok": False, "reason": "unsupported",
            }
            return False
        return self._apply_gain(path, value)

    def gain_available(self):
        return self._gain_path() is not None

    def restore_gain(self, value):
        operation = self._last_operation
        applied = self.apply_gain(value)
        if operation is not None:
            self._last_operation = operation
        return applied

    def apply(self, patch):
        if not isinstance(patch, dict):
            return False
        if self._xbox_state() is not None:
            applied = self._xbox.apply(patch)
            self._last_operation = self._xbox.diagnostics()
            return applied
        lenovo = self._lenovo_state()
        if lenovo is not None:
            applied = self._lenovo.apply(patch)
            self._last_operation = self._lenovo.diagnostics()
            if applied:
                current = self._lenovo.state()
                if current is not None:
                    self._lenovo_last_state = dict(current)
            return applied
        asus_path = self._asus_path()
        if asus_path is not None:
            return self._apply_dual(asus_path, patch)
        gain_path = self._gain_path()
        if gain_path is not None:
            return self._apply_gain(gain_path, patch.get("value"))
        self._last_operation = {
            "mode": None, "ok": False, "reason": "unsupported",
        }
        return False
