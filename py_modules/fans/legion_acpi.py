"""Legion Go original (83E1) fan control via acpi_call -> \\_SB.GZFD (HHD's path).

Pure encoders/decoders for the GameZone WMI methods:
  WMAB 0x06  set 10-point fan curve      WMAB 0x05  get curve
  WMAE 0x12  set_feature(0x04020000,v)   full fan speed on/off ("a tope")
The firmware runs the written curve autonomously, so this is a HARDWARE-curve
backend (no software loop, no event-loop risk).
"""

import os
from typing import Optional

import acpi_call as _acpi_call
from fans.control import _interp

# Fixed firmware temp anchors (°C). Only the 10 speed bytes are ever substituted.
ANCHORS = (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)
# Per-point safety floor (percent) at those anchors: clamp UP, never reject.
MIN_CURVE = [44, 48, 55, 60, 71, 79, 87, 87, 100, 100]

GZFD = r"\_SB.GZFD"
_SET_CURVE_ID = "0x06"
_GET_CURVE_ID = "0x05"
_SET_FEATURE_ID = "0x12"
_FULL_SPEED_FEATURE = 0x04020000

_READBACK_TOLERANCE = 5   # firmware may quantize speed to a coarse grid


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
    """Parse an acpi_call byte-buffer response '{0x.., 0x.., ...}' -> [int]. Returns
    None for None / non-buffer results ('not called', an int, an error token)."""
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
    """The 10 active speeds are at byte offsets 4,8,...,40 (stride 4 — NOT the
    stride-2 write layout). Returns None if the response is too short / junk."""
    b = parse_acpi_bytes(resp)
    if b is None or len(b) < 41:
        return None
    return [b[i] for i in range(4, 44, 4)]


def clamp_floor(speeds: list) -> list:
    """Clamp each point to [MIN_CURVE[i], 100]. Never rejects a curve."""
    return [max(min(int(s), 100), MIN_CURVE[i]) for i, s in enumerate(speeds)]


def curve_to_speeds(points: list) -> list:
    """Canonical temp->pwm(0-255) curve -> 10 firmware speeds (percent), resampled at
    the fixed anchors, then floored to MIN_CURVE."""
    pcts = [round(_interp(points, t) / 255 * 100) for t in ANCHORS]
    return clamp_floor(pcts)


class LegionAcpiCallFanBackend:
    """Legion Go original (83E1) fan curve + full-speed via acpi_call -> \\_SB.GZFD.

    Hardware-curve backend (firmware runs the table; no software loop). Support is
    decided cheaply (acpi_call available) on construction; the modprobe + GET-curve
    probe run lazily on the first drive, off the event loop. Never fakes success:
    every curve write is verified by a GET readback against the clamped values.
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
        self._drove_curve = False   # True once we've written a manual curve
        self._max_on = False

    # --- support / lifecycle ------------------------------------------------

    @property
    def supported(self) -> bool:
        # Optimistic before the probe (acpi available); truthful after it.
        if not self._available:
            return False
        return (not self._primed) or self._probe_ok

    def _ensure_loaded(self) -> bool:
        # Off-loop only (spawns modprobe). Self-healing: never latch a failure.
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
        and capture the stock curve for restore. Safe to call repeatedly."""
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

    # --- public dict API ----------------------------------------------------

    def read_state(self) -> dict:
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}
        speeds = self._last_speeds or [0] * 10
        points = [{"temp": ANCHORS[i], "pwm": round(speeds[i] / 100 * 255)} for i in range(10)]
        # Manual (1) only when WE are actually driving; a plain prime GET leaves the
        # fan on firmware auto (2), even though it populated the displayed curve.
        enable = 1 if (self._drove_curve or self._max_on) else 2
        return {"supported": True, "source": self.name, "pwm_max": 255,
                "fans": [{"key": "fan", "enable": enable, "points": points}]}

    def set_curve(self, fan_key: str, points: list) -> dict:
        if not self._available:
            return {"ok": False, "detail": "acpi_call unavailable"}
        if not self._ensure_loaded():
            return {"ok": False, "detail": "acpi_call could not be loaded"}
        speeds = curve_to_speeds(points)
        # Capture the stock curve once, and let a too-old BIOS (no GZFD methods) fail
        # honestly via the GET probe before we claim a write took.
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
        # We issued the write, so we now own the fan and must restore stock on release,
        # regardless of whether the readback confirms (a coarse-quantizing firmware can
        # read back off by more than the tolerance even when the write landed). The
        # readback only decides what we honestly report to the caller.
        self._last_speeds = speeds
        self._drove_curve = True
        got = self._get_speeds()
        if got is None or any(abs(got[i] - speeds[i]) > _READBACK_TOLERANCE for i in range(10)):
            return {"ok": False, "detail": "readback did not confirm curve"}
        return {"ok": True, "detail": "fan curve applied (GZFD)"}

    def apply_curve_all(self, points: list) -> dict:
        # The 83E1 has a single fan.
        return self.set_curve("fan", points)

    def set_max(self, on: bool) -> dict:
        if not self._available:
            return {"ok": False, "detail": "acpi_call unavailable"}
        if not self._ensure_loaded():
            return {"ok": False, "detail": "acpi_call could not be loaded"}
        self._call(f"{GZFD}.WMAE 0x00 {_SET_FEATURE_ID} {encode_set_max(bool(on))}")
        self._max_on = bool(on)
        return {"ok": True, "detail": f"full fan speed {'on' if on else 'off'}"}

    def set_auto(self, fan_key: Optional[str] = None) -> dict:
        # There is no firmware manual/auto bit on the 83E1, so 'auto' means: undo what
        # WE changed and leave the firmware exactly as we found it. Clear full-speed,
        # and write back the stock curve captured before our first write — only if we
        # actually drove a curve. If we never touched the fan, this is a no-op (never
        # write MIN_CURVE here: it would floor the idle fan louder than stock).
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
