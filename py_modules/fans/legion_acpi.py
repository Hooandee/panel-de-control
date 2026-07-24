"""Legion Go original (83E1) fan control via acpi_call -> \\_SB.GZFD (HHD's path).

Encoders for the GameZone WMI methods (WMAB 0x06/0x05 curve set/get, WMAE 0x12
full-speed) plus a hardware-curve backend: the firmware runs the written table
itself, so there is no software loop.
"""

import os
from typing import Optional

import acpi_call as _acpi_call
from fans.control import _interp

ANCHORS = (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)   # fixed firmware temp anchors (°C)
MIN_CURVE = [44, 48, 55, 60, 71, 79, 87, 87, 100, 100]   # per-point floor (percent)

GZFD = r"\_SB.GZFD"
_SET_CURVE_ID = "0x06"
_GET_CURVE_ID = "0x05"
_SET_FEATURE_ID = "0x12"
_FULL_SPEED_FEATURE = 0x04020000

_READBACK_TOLERANCE = 5


def encode_set_curve(speeds: list) -> str:
    """52-byte SET buffer: header + 10 speeds (u16 LE) + temp sub-header + 10 fixed
    temps (u16 LE) + pad. *speeds* are 10 ints 0-100."""
    buf = bytearray([0x00, 0x00, 0x0A, 0x00, 0x00, 0x00])
    for s in speeds:
        buf += bytes([int(s) & 0xFF, 0x00])
    buf += bytes([0x00, 0x0A, 0x00, 0x00, 0x00])
    for t in ANCHORS:
        buf += bytes([t & 0xFF, 0x00])
    buf += bytes([0x00])
    return "b" + buf.hex()


def encode_get_curve() -> str:
    return "b00000000"


def encode_set_max(on: bool) -> str:
    """set_feature(0x04020000, 1|0): id LE32 ++ value LE32."""
    fid = _FULL_SPEED_FEATURE
    val = 1 if on else 0
    body = bytes((fid & 0xFF, (fid >> 8) & 0xFF, (fid >> 16) & 0xFF, (fid >> 24) & 0xFF,
                  val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF, (val >> 24) & 0xFF))
    return "b" + body.hex()


def parse_acpi_bytes(resp) -> Optional[list]:
    """Parse an acpi_call byte-buffer response '{0x.., ...}' -> [int]; None for a
    non-buffer result (None, 'not called', an int, an error token)."""
    if not resp:
        return None
    s = str(resp).strip().strip("\x00").strip()
    if not (s.startswith("{") and s.endswith("}")):
        return None
    inner = s[1:-1].strip()
    if not inner:
        return []
    out = []
    for tok in inner.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(int(tok, 0) & 0xFF)
        except ValueError:
            return None
    return out


def decode_get_curve(resp) -> Optional[list]:
    """The 10 active speeds sit at byte offsets 4,8,...,40 (stride 4, unlike the
    stride-2 write layout). None if the response is too short or junk."""
    b = parse_acpi_bytes(resp)
    if b is None or len(b) < 41:
        return None
    return [b[i] for i in range(4, 44, 4)]


def clamp_floor(speeds: list) -> list:
    return [max(min(int(s), 100), MIN_CURVE[i]) for i, s in enumerate(speeds)]


def curve_to_speeds(points: list) -> list:
    """Canonical temp->pwm(0-255) curve -> 10 firmware speeds (percent), resampled at
    the fixed anchors, then floored to MIN_CURVE."""
    pcts = [round(_interp(points, t) / 255 * 100) for t in ANCHORS]
    return clamp_floor(pcts)


class LegionAcpiCallFanBackend:
    """Legion Go original (83E1) fan curve + full-speed via acpi_call -> \\_SB.GZFD.

    Support is decided cheaply on construction (acpi_call available); the modprobe
    and GET-curve probe run lazily on the first drive, off the event loop. Each curve
    write is verified by a GET readback.
    """

    name = "legion-acpi-gzfd"
    supports_max = True
    resettable = False

    def __init__(self, root: str = "/", caller=None, modprobe=None) -> None:
        self._root = root
        self._call_path = os.path.join(root, _acpi_call.CALL_REL)
        self._call = caller or (lambda cmd: _acpi_call.serialized_call(self._call_path, cmd))
        self._modprobe = modprobe or _acpi_call.default_modprobe
        self._available = _acpi_call.available(root)
        self._loaded = _acpi_call.node_writable(root)
        self._primed = False
        self._probe_ok = False
        self._stock_speeds: Optional[list] = None
        self._last_speeds: Optional[list] = None
        self._drove_curve = False
        self._max_on = False

    @property
    def supported(self) -> bool:
        if not self._available:
            return False
        return (not self._primed) or self._probe_ok

    def _ensure_loaded(self) -> bool:
        # Spawns modprobe -> off-loop callers only. Self-healing: never latch a failure.
        if self._loaded:
            return True
        if _acpi_call.node_writable(self._root):
            self._loaded = True
            return True
        try:
            self._modprobe("acpi_call")
        except Exception:  # noqa: BLE001
            return False
        self._loaded = _acpi_call.node_writable(self._root)
        return self._loaded

    def _get_speeds(self) -> Optional[list]:
        return decode_get_curve(
            self._call(f"{GZFD}.WMAB 0x00 {_GET_CURVE_ID} {encode_get_curve()}"))

    def prime(self) -> None:
        """One-time off-loop probe: modprobe, GET the curve to prove the method works,
        and capture the stock curve for restore."""
        if self._primed or not self._available:
            return
        if not self._ensure_loaded():
            return
        speeds = self._get_speeds()
        self._primed = True
        if speeds is not None:
            self._probe_ok = True
            self._last_speeds = speeds
            if self._stock_speeds is None:
                self._stock_speeds = list(speeds)

    def read_state(self) -> dict:
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}
        speeds = self._last_speeds or [0] * 10
        points = [{"temp": ANCHORS[i], "pwm": round(speeds[i] / 100 * 255)} for i in range(10)]
        enable = 1 if (self._drove_curve or self._max_on) else 2
        return {"supported": True, "source": self.name, "pwm_max": 255,
                "fans": [{"key": "fan", "enable": enable, "points": points}]}

    def set_curve(self, fan_key: str, points: list) -> dict:
        if not self._available:
            return {"ok": False, "detail": "acpi_call unavailable"}
        if not self._ensure_loaded():
            return {"ok": False, "detail": "acpi_call could not be loaded"}
        speeds = curve_to_speeds(points)
        # First time only: GET to prove the method exists and capture stock (the
        # post-write readback still catches a dead node on later calls).
        if not self._probe_ok or self._stock_speeds is None:
            current = self._get_speeds()
            if current is None:
                self._primed = True
                self._probe_ok = False
                return {"ok": False, "detail": "GZFD fan method not available (BIOS too old?)"}
            self._probe_ok = True
            self._primed = True
            if self._stock_speeds is None:
                self._stock_speeds = list(current)
        self._call(f"{GZFD}.WMAB 0x00 {_SET_CURVE_ID} {encode_set_curve(speeds)}")
        # Own the fan the moment we write (must precede the readback): a coarse firmware
        # can read back beyond tolerance even when the write landed — restore must run.
        self._last_speeds = speeds
        self._drove_curve = True
        got = self._get_speeds()
        if got is None or any(abs(got[i] - speeds[i]) > _READBACK_TOLERANCE for i in range(10)):
            return {"ok": False, "detail": "readback did not confirm curve"}
        return {"ok": True, "detail": "fan curve applied (GZFD)"}

    def apply_curve_all(self, points: list) -> dict:
        return self.set_curve("fan", points)   # single fan on the 83E1

    def set_max(self, on: bool) -> dict:
        if not self._available:
            return {"ok": False, "detail": "acpi_call unavailable"}
        if not self._ensure_loaded():
            return {"ok": False, "detail": "acpi_call could not be loaded"}
        self._call(f"{GZFD}.WMAE 0x00 {_SET_FEATURE_ID} {encode_set_max(bool(on))}")
        self._max_on = bool(on)
        return {"ok": True, "detail": f"full fan speed {'on' if on else 'off'}"}

    def set_auto(self, fan_key: Optional[str] = None) -> dict:
        # No firmware auto bit on the 83E1: restore the stock curve captured before our
        # first write, and only if we drove one. Never write MIN_CURVE here — it would
        # floor the idle fan louder than the firmware baseline.
        if not self._available:
            return {"ok": False, "detail": "acpi_call unavailable"}
        if not self._ensure_loaded():
            return {"ok": False, "detail": "acpi_call could not be loaded"}
        if self._max_on:
            self.set_max(False)
        if self._drove_curve and self._stock_speeds is not None:
            self._call(f"{GZFD}.WMAB 0x00 {_SET_CURVE_ID} {encode_set_curve(self._stock_speeds)}")
            self._drove_curve = False
        self._last_speeds = None
        return {"ok": True, "detail": "fan returned to firmware baseline"}

    def restore_auto(self) -> dict:
        return self.set_auto(None)
