"""GPU clock control (min/max MHz), per vendor.

AMD (amdgpu): the OverDrive interface — write `power_dpm_force_performance_level=
manual`, then `s 0 <min>` / `s 1 <max>` / `c` to `pp_od_clk_voltage`; the allowed
range comes from that file's OD_RANGE section. Auto = performance_level back to auto.

Intel (i915): plain `gt_min_freq_mhz` / `gt_max_freq_mhz`; hardware bounds are
`gt_RPn_freq_mhz` (min) / `gt_RP0_freq_mhz` (max); auto = restore the full range.

Pure parsing/command building is unit-tested. Every backend degrades to unsupported
(UI hidden) when the nodes are absent."""
import glob
import os
import re

from sysfs import read_int, read_str, write_str

_DRM = "sys/class/drm"


def parse_od_range(text):
    """The (min, max) SCLK bounds from a pp_od_clk_voltage dump, or None."""
    if not text:
        return None
    m = re.search(r"SCLK:\s*(\d+)\s*Mhz\s+(\d+)\s*Mhz", text, re.IGNORECASE)
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_od_sclk(text):
    """The current forced (min, max) SCLK from the OD_SCLK section, or None."""
    if not text:
        return None
    vals = re.findall(r"^\s*\d+:\s*(\d+)\s*Mhz", text, re.IGNORECASE | re.MULTILINE)
    return (int(vals[0]), int(vals[1])) if len(vals) >= 2 else None


def sclk_commands(min_mhz, max_mhz):
    """The pp_od_clk_voltage command sequence to pin the SCLK window then commit."""
    return [f"s 0 {int(min_mhz)}", f"s 1 {int(max_mhz)}", "c"]


def _window(value):
    if not value:
        return None
    return {"min_mhz": int(value[0]), "max_mhz": int(value[1])}


class _GpuDiagnostics:
    backend = "unknown"

    def _record(self, action, requested, ok, reason=""):
        try:
            applied = self.get()
        except Exception:  # noqa: BLE001 - diagnostics must not mask the operation
            applied = None
        self._last_operation = {
            "action": action,
            "requested": _window(requested),
            "applied": _window(applied),
            "ok": bool(ok),
            "reason": reason,
        }

    def diagnostics(self):
        try:
            hardware_range = self.get_range()
        except Exception:  # noqa: BLE001
            hardware_range = None
        try:
            applied = self.get()
        except Exception:  # noqa: BLE001
            applied = None
        return {
            "backend": self.backend,
            "supported": bool(self.supported),
            "range": _window(hardware_range),
            "applied": _window(applied),
            "last_operation": getattr(self, "_last_operation", None),
        }


class NullGpuClock(_GpuDiagnostics):
    supported = False
    backend = "none"

    def get_range(self):
        return None

    def get(self):
        return None

    def set(self, min_mhz, max_mhz):
        return False

    def set_auto(self):
        return False


class AmdGpuClock(_GpuDiagnostics):
    backend = "amdgpu"

    def __init__(self, root="/"):
        self._last_operation = None
        self._od = None
        self._level = None
        for od in glob.glob(os.path.join(root, _DRM, "card[0-9]*", "device", "pp_od_clk_voltage")):
            if parse_od_range(read_str(od)) is not None:
                self._od = od
                self._level = os.path.join(os.path.dirname(od), "power_dpm_force_performance_level")
                break
        self.supported = self._od is not None and read_str(self._level) is not None

    def get_range(self):
        return parse_od_range(read_str(self._od)) if self.supported else None

    def get(self):
        return parse_od_sclk(read_str(self._od)) if self.supported else None

    def set(self, min_mhz, max_mhz):
        if not self.supported:
            self._record("manual", (min_mhz, max_mhz), False, "unsupported")
            return False
        try:
            write_str(self._level, "manual")
            for cmd in sclk_commands(min_mhz, max_mhz):
                write_str(self._od, cmd)
            ok = read_str(self._level) == "manual"
            self._record("manual", (min_mhz, max_mhz), ok,
                         "" if ok else "readback_mismatch")
            return ok
        except Exception as exc:  # noqa: BLE001
            self._record("manual", (min_mhz, max_mhz), False, type(exc).__name__)
            return False

    def set_auto(self):
        if not self.supported:
            self._record("auto", None, False, "unsupported")
            return False
        try:
            write_str(self._level, "auto")
            ok = read_str(self._level) == "auto"
            self._record("auto", self.get_range(), ok,
                         "" if ok else "readback_mismatch")
            return ok
        except Exception as exc:  # noqa: BLE001
            self._record("auto", None, False, type(exc).__name__)
            return False


class _FreqPairClock(_GpuDiagnostics):
    """Shared min/max GPU-frequency backend for the Intel drivers, which both expose
    a writable min/max pair + hardware RPn/RP0 bounds — only the node names/location
    differ (i915 vs xe). A subclass sets `self._min/_max/_rpn/_rp0` to the four full
    paths (or leaves them None → unsupported)."""

    _min = _max = _rpn = _rp0 = None

    @property
    def supported(self):
        return self._max is not None and read_int(self._max) is not None

    def get_range(self):
        if not self.supported:
            return None
        lo, hi = read_int(self._rpn), read_int(self._rp0)
        return (lo, hi) if lo is not None and hi is not None else None

    def get(self):
        if not self.supported:
            return None
        lo, hi = read_int(self._min), read_int(self._max)
        return (lo, hi) if lo is not None and hi is not None else None

    def set(self, min_mhz, max_mhz):
        if not self.supported:
            self._record("manual", (min_mhz, max_mhz), False, "unsupported")
            return False
        lo, hi = int(min_mhz), int(max_mhz)
        # The driver enforces min <= max at write time. Writing the two nodes in the
        # wrong order transiently violates that (new min > current max, or new max <
        # current min) and the kernel rejects one write. Raising the window → set max
        # first; lowering (or unknown) → set min first.
        try:
            cur = self.get()
            if cur and lo > cur[1]:
                write_str(self._max, hi)
                write_str(self._min, lo)
            else:
                write_str(self._min, lo)
                write_str(self._max, hi)
            ok = self.get() == (lo, hi)
            self._record("manual", (lo, hi), ok,
                         "" if ok else "readback_mismatch")
            return ok
        except Exception as exc:  # noqa: BLE001
            self._record("manual", (lo, hi), False, type(exc).__name__)
            return False

    def set_auto(self):
        rng = self.get_range()
        if not rng:
            self._record("auto", None, False, "range_unavailable")
            return False
        ok = self.set(*rng)
        operation = getattr(self, "_last_operation", None)
        if operation is not None:
            operation["action"] = "auto"
        return ok


class IntelGpuClock(_FreqPairClock):
    """i915: /sys/class/drm/card*/gt_{min,max,RPn,RP0}_freq_mhz."""

    backend = "i915"

    def __init__(self, root="/"):
        self._last_operation = None
        for maxp in sorted(glob.glob(os.path.join(root, _DRM, "card[0-9]*", "gt_max_freq_mhz"))):
            d = os.path.dirname(maxp)
            self._min = os.path.join(d, "gt_min_freq_mhz")
            self._max = maxp
            self._rpn = os.path.join(d, "gt_RPn_freq_mhz")
            self._rp0 = os.path.join(d, "gt_RP0_freq_mhz")
            break


class XeGpuClock(_FreqPairClock):
    """xe (Lunar Lake / MSI Claw): card*/device/tile*/gt*/freq0/{min,max,rpn,rp0}_freq.
    Targets gt0 (the render GT) — the sorted glob puts gt0 before gt1."""

    backend = "xe"

    def __init__(self, root="/"):
        self._last_operation = None
        pattern = os.path.join(root, _DRM, "card[0-9]*", "device", "tile*", "gt*", "freq0", "max_freq")
        for maxp in sorted(glob.glob(pattern)):
            d = os.path.dirname(maxp)
            self._min = os.path.join(d, "min_freq")
            self._max = maxp
            self._rpn = os.path.join(d, "rpn_freq")
            self._rp0 = os.path.join(d, "rp0_freq")
            break


def select_gpu_clock(device, root="/"):
    """AMD → amdgpu OverDrive; Intel → xe (newer) then i915; else Null."""
    order = (XeGpuClock, IntelGpuClock, AmdGpuClock) if getattr(device, "vendor", "amd") == "intel" \
        else (AmdGpuClock, XeGpuClock, IntelGpuClock)
    for cls in order:
        backend = cls(root)
        if backend.supported:
            return backend
    return NullGpuClock()
