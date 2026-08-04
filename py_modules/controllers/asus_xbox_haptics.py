import glob
import math
import os
import time


_DEVICE_KEY = "rog_xbox_ally_x"
_HID_ID = "HID_ID=0003:00000B05:00001B4C"
_APPLICATIONS = {0x000F0002, 0x000F0021, 0x00010005}
_REPORT_ID = 0x0D
_NATIVE_MAX = 64
_STALE_READBACK_MAX = 100
_CHANNELS = {
    "trigger_left": (0x01, 0),
    "trigger_right": (0x02, 1),
    "strong": (0x04, 2),
    "weak": (0x08, 3),
}
_HD_FIELDS = (
    "hd_game_enabled", "trigger_left", "trigger_right",
    "trigger_left_source", "trigger_right_source",
)


def build_rumble_report(channel, strength):
    if channel == "all":
        enable = 0x0F
        magnitudes = [strength] * 4
    else:
        enable, index = _CHANNELS[channel]
        magnitudes = [0, 0, 0, 0]
        magnitudes[index] = strength
    return bytes([
        _REPORT_ID,
        enable,
        *magnitudes,
        0xFF,
        0x00,
        0xEB,
    ])


def _descriptor_has_rumble_output(descriptor):
    usage_page = 0
    usage = None
    report_id = 0
    applications = []
    index = 0
    while index < len(descriptor):
        prefix = descriptor[index]
        index += 1
        if prefix == 0xFE:
            if index + 2 > len(descriptor):
                return False
            size = descriptor[index]
            index += 2 + size
            continue
        size_code = prefix & 0x03
        size = 4 if size_code == 3 else size_code
        if index + size > len(descriptor):
            return False
        value = int.from_bytes(descriptor[index:index + size], "little")
        index += size
        item_type = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        if item_type == 1 and tag == 0:
            usage_page = value
        elif item_type == 1 and tag == 8:
            report_id = value
        elif item_type == 2 and tag == 0:
            usage = value
        elif item_type == 0 and tag == 10:
            parent = applications[-1] if applications else None
            application = (
                (usage_page << 16) | usage
                if value == 1 and usage is not None
                else parent
            )
            applications.append(application)
            usage = None
        elif item_type == 0 and tag == 12:
            if applications:
                applications.pop()
        elif item_type == 0 and tag == 9:
            application = applications[-1] if applications else None
            if report_id == _REPORT_ID and application in _APPLICATIONS:
                return True
    return False


def _default_write_text(path, value):
    with open(path, "w") as stream:
        stream.write(value)


def _default_write_report(path, report):
    descriptor = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    try:
        return os.write(descriptor, report)
    finally:
        os.close(descriptor)


class AsusXboxHapticsAdapter:
    def __init__(
        self,
        device_key,
        root="/",
        write_text=None,
        write_report=None,
        sleep=None,
        dbus=None,
    ):
        self._device_key = device_key or ""
        self._root = root
        self._write_text = write_text or _default_write_text
        self._write_report = write_report or _default_write_report
        self._sleep = sleep or time.sleep
        self._dbus = dbus
        self._last_operation = None

    def _path(self, absolute):
        return os.path.join(self._root, absolute.lstrip("/"))

    def _intensity_path(self):
        if self._device_key != _DEVICE_KEY:
            return None
        matches = glob.glob(self._path(
            "/sys/bus/hid/drivers/asus_rog_ally/"
            "*0B05:1B4C*/vibration_intensity"
        ))
        return matches[0] if len(matches) == 1 else None

    def _hidraw_path(self):
        if self._device_key != _DEVICE_KEY:
            return None
        matches = []
        for hidraw in glob.glob(self._path("/sys/class/hidraw/hidraw*")):
            try:
                with open(os.path.join(hidraw, "device/uevent")) as stream:
                    identity = stream.read().splitlines()
                with open(
                    os.path.join(hidraw, "device/report_descriptor"), "rb"
                ) as stream:
                    descriptor = stream.read()
            except OSError:
                continue
            if _HID_ID not in identity:
                continue
            if not _descriptor_has_rumble_output(descriptor):
                continue
            candidate = self._path(
                f"/dev/{os.path.basename(hidraw)}"
            )
            if os.path.exists(candidate):
                matches.append(candidate)
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _read_native(path):
        try:
            with open(path) as stream:
                values = [int(value) for value in stream.read().split()]
        except (OSError, ValueError):
            return None
        if len(values) != 2 or any(
            value < 0 or value > _STALE_READBACK_MAX for value in values
        ):
            return None
        # SteamOS may expose the firmware default as 100 even though the
        # driver's store contract only accepts values up to 64.
        return tuple(min(value, _NATIVE_MAX) for value in values)

    @staticmethod
    def _percent(native):
        return min(100, round((native * 100 / _NATIVE_MAX) / 5) * 5)

    @staticmethod
    def _native(percent):
        return round(percent * _NATIVE_MAX / 100)

    @staticmethod
    def _clean_percent(value):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            return None
        return min(100, max(0, round(float(value) / 5) * 5))

    def state(self):
        path = self._intensity_path()
        values = self._read_native(path) if path is not None else None
        if values is None:
            return None
        state = {
            "mode": "asus_xbox_hd",
            "persistent": True,
            "left": self._percent(values[0]),
            "right": self._percent(values[1]),
            "min": 0,
            "max": 100,
            "step": 5,
            "readback": True,
            "connected": True,
        }
        hd_state = getattr(
            self._dbus, "xbox_hd_haptics", lambda: None
        )()
        if isinstance(hd_state, dict):
            state.update({
                "hd_game_supported": True,
                "hd_game_enabled": hd_state["enabled"],
                **{
                    field: hd_state[field]
                    for field in (
                        "trigger_left", "trigger_right",
                        "trigger_left_source", "trigger_right_source",
                    )
                },
            })
        else:
            state["hd_game_supported"] = False
        return state

    def capabilities(self, state=None):
        if state is None:
            state = self.state()
        if state is None:
            return None
        test_available = self._hidraw_path() is not None
        return {
            "mode": "asus_xbox_hd",
            "channels": ["left", "right"],
            "readback": "driver",
            "min": 0,
            "max": 100,
            "step": 5,
            "hd_game_supported": state.get("hd_game_supported", False),
            "trigger_source_options": ["off", "strong", "weak", "mix"],
            "test": {
                "patterns": ["pulse"] if test_available else [],
                "channels": list(_CHANNELS) + ["all"] if test_available else [],
            },
        }

    def snapshot(self):
        state = self.state()
        return {
            "state": state,
            "capabilities": self.capabilities(state) if state is not None else None,
        }

    def capture_baseline(self):
        path = self._intensity_path()
        values = self._read_native(path) if path is not None else None
        if values is None:
            return {}
        baseline = {"native_left": values[0], "native_right": values[1]}
        read_hd = getattr(self._dbus, "xbox_hd_haptics", None)
        hd = read_hd() if callable(read_hd) else None
        if isinstance(hd, dict):
            baseline.update({
                "hd_game_enabled": hd["enabled"],
                **{field: hd[field] for field in _HD_FIELDS[1:]},
            })
        return baseline

    def _write_native(self, values):
        path = self._intensity_path()
        current = self._read_native(path) if path is not None else None
        if path is None or current is None:
            self._last_operation = {
                "mode": "asus_xbox_hd", "ok": False,
                "reason": "initial_readback_unavailable",
            }
            return False
        try:
            self._write_text(path, f"{values[0]} {values[1]}\n")
        except OSError:
            self._last_operation = {
                "mode": "asus_xbox_hd", "ok": False,
                "reason": "write_failed",
            }
            return False
        if self._read_native(path) == values:
            self._last_operation = {
                "mode": "asus_xbox_hd", "ok": True, "readback": True,
            }
            return True
        rollback_confirmed = False
        try:
            self._write_text(path, f"{current[0]} {current[1]}\n")
            rollback_confirmed = self._read_native(path) == current
        except OSError:
            pass
        self._last_operation = {
            "mode": "asus_xbox_hd", "ok": False,
            "reason": "readback_mismatch",
            "rollback_confirmed": rollback_confirmed,
        }
        return False

    def apply(self, patch):
        left = self._clean_percent(patch.get("left"))
        right = self._clean_percent(patch.get("right"))
        if left is None or right is None:
            self._last_operation = {
                "mode": "asus_xbox_hd", "ok": False,
                "reason": "invalid_value",
            }
            return False
        body_baseline = self.capture_baseline()
        body_applied = self._write_native((self._native(left), self._native(right)))
        if not body_applied:
            return False
        if not all(field in patch for field in _HD_FIELDS):
            return True
        apply_hd = getattr(self._dbus, "set_xbox_hd_haptics", None)
        read_hd = getattr(self._dbus, "xbox_hd_haptics", None)
        hd_baseline = read_hd() if callable(read_hd) else None
        requested = {
            "enabled": patch["hd_game_enabled"],
            **{field: patch[field] for field in _HD_FIELDS[1:]},
        }
        hd_applied = bool(callable(apply_hd) and apply_hd(requested))
        if hd_applied and callable(read_hd) and read_hd() == requested:
            self._last_operation = {
                "mode": "asus_xbox_hd", "ok": True, "readback": True,
            }
            return True
        body_restored = self.restore_baseline(body_baseline)
        hd_restored = True
        if isinstance(hd_baseline, dict) and callable(read_hd):
            hd_restored = read_hd() == hd_baseline
            if not hd_restored and callable(apply_hd):
                hd_restored = bool(
                    apply_hd(hd_baseline) and read_hd() == hd_baseline
                )
        self._last_operation = {
            "mode": "asus_xbox_hd",
            "ok": False,
            "reason": (
                "hd_readback_mismatch" if hd_applied
                else "hd_apply_failed"
            ),
            "rollback_confirmed": body_restored and hd_restored,
        }
        return False

    def restore_baseline(self, baseline):
        if not isinstance(baseline, dict):
            return False
        values = (baseline.get("native_left"), baseline.get("native_right"))
        if not all(
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value <= _NATIVE_MAX
            for value in values
        ):
            return False
        current = self.capture_baseline()
        if not self._write_native(values):
            return False
        if not all(field in baseline for field in _HD_FIELDS):
            return True
        apply_hd = getattr(self._dbus, "set_xbox_hd_haptics", None)
        read_hd = getattr(self._dbus, "xbox_hd_haptics", None)
        requested = {
            "enabled": baseline["hd_game_enabled"],
            **{field: baseline[field] for field in _HD_FIELDS[1:]},
        }
        if callable(read_hd) and read_hd() == requested:
            self._last_operation = {
                "mode": "asus_xbox_hd", "ok": True, "readback": True,
            }
            return True
        if (
            callable(apply_hd)
            and callable(read_hd)
            and apply_hd(requested)
            and read_hd() == requested
        ):
            self._last_operation = {
                "mode": "asus_xbox_hd", "ok": True, "readback": True,
            }
            return True
        body_rollback = self._write_native((
            current.get("native_left"), current.get("native_right")
        ))
        hd_rollback = False
        if all(field in current for field in _HD_FIELDS):
            previous_hd = {
                "enabled": current["hd_game_enabled"],
                **{field: current[field] for field in _HD_FIELDS[1:]},
            }
            hd_rollback = bool(
                callable(apply_hd)
                and callable(read_hd)
                and apply_hd(previous_hd)
                and read_hd() == previous_hd
            )
        self._last_operation = {
            "mode": "asus_xbox_hd",
            "ok": False,
            "reason": "hd_restore_failed",
            "rollback_confirmed": body_rollback and hd_rollback,
        }
        return False

    @staticmethod
    def _test_result(sent, stopped, reason):
        return {
            "sent": sent,
            "stopped": stopped,
            "restored": stopped,
            "reason": reason,
        }

    def test(self, pattern, channel, strength):
        if pattern != "pulse":
            return self._test_result(False, False, "unsupported_pattern")
        if (
            not isinstance(strength, int)
            or isinstance(strength, bool)
            or not 0 <= strength <= 100
        ):
            return self._test_result(False, False, "invalid_strength")
        path = self._hidraw_path()
        allowed = set(_CHANNELS) | {"all"}
        if path is None or channel not in allowed:
            return self._test_result(False, False, "unsupported_channel")
        state = self.state()
        disabled_triggers = {
            trigger
            for trigger in ("trigger_left", "trigger_right")
            if isinstance(state, dict)
            and state.get("hd_game_supported") is True
            and (
                state.get(trigger) == 0
                or state.get(f"{trigger}_source") == "off"
            )
        }
        if channel in disabled_triggers or (
            channel == "all" and disabled_triggers
        ):
            stop = build_rumble_report("all", 0)
            try:
                stopped = self._write_report(path, stop) == len(stop)
            except OSError:
                stopped = False
            reason = "motor_disabled" if stopped else "stop_failed"
            result = self._test_result(False, stopped, reason)
            self._last_operation = {
                "mode": "asus_xbox_hd", "ok": stopped, "test": result,
            }
            return result
        sent = False
        stopped = False
        try:
            report = build_rumble_report(channel, strength)
            sent = self._write_report(path, report) == len(report)
            if sent:
                self._sleep(0.18)
        except OSError:
            sent = False
        finally:
            stop = build_rumble_report("all", 0)
            try:
                stopped = self._write_report(path, stop) == len(stop)
            except OSError:
                stopped = False
        reason = None if sent and stopped else (
            "stop_failed" if sent else "start_failed"
        )
        self._last_operation = {
            "mode": "asus_xbox_hd", "ok": reason is None,
            "test": self._test_result(sent, stopped, reason),
        }
        return self._test_result(sent, stopped, reason)

    def diagnostics(self):
        return dict(self._last_operation) if self._last_operation else None
