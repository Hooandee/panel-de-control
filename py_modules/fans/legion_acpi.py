"""Legion Go original (83E1) fan control via acpi_call -> \\_SB.GZFD (HHD's path).

Pure encoders/decoders for the GameZone WMI methods (facts only, no GPL code):
  WMAB 0x06  set 10-point fan curve      WMAB 0x05  get curve
  WMAE 0x12  set_feature(0x04020000,v)   full fan speed on/off ("a tope")
The firmware runs the written curve autonomously, so this is a HARDWARE-curve
backend (no software loop, no event-loop risk).
"""

from typing import Optional

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

_READBACK_TOLERANCE = 3   # firmware may round a percent by a couple of points


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
