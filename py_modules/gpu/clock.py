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
        except Exception:  # noqa: BLE001
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
            "selection": [
                dict(row) for row in getattr(self, "_selection", ())
            ],
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

    def capture_state(self):
        return None

    def restore_state(self, state):
        return False


class AmdGpuClock(_GpuDiagnostics):
    backend = "amdgpu"

    def __init__(self, root="/"):
        self._last_operation = None
        self._od = None
        self._level = None
        for od in sorted(glob.glob(
            os.path.join(root, _DRM, "card[0-9]*", "device", "pp_od_clk_voltage")
        )):
            level = os.path.join(
                os.path.dirname(od), "power_dpm_force_performance_level"
            )
            contents = read_str(od)
            if (
                parse_od_range(contents) is not None
                and parse_od_sclk(contents) is not None
                and read_str(level) is not None
                and os.access(od, os.W_OK)
                and os.access(level, os.W_OK)
            ):
                self._od = od
                self._level = level
                break
        self.supported = self._od is not None

    def get_range(self):
        return parse_od_range(read_str(self._od)) if self.supported else None

    def get(self):
        return parse_od_sclk(read_str(self._od)) if self.supported else None

    def capture_state(self):
        if not self.supported:
            return None
        level = read_str(self._level)
        window = self.get()
        if level is None or window is None:
            return None
        return {"level": level, "window": window}

    def restore_state(self, state):
        if not isinstance(state, dict):
            return False
        window = state.get("window")
        if (
            state.get("level") is None
            or not isinstance(window, (list, tuple))
            or len(window) != 2
        ):
            return False
        return self._restore(state["level"], tuple(window))

    def set(self, min_mhz, max_mhz):
        if not self.supported:
            self._record("manual", (min_mhz, max_mhz), False, "unsupported")
            return False
        previous_level = read_str(self._level)
        previous_window = self.get()
        try:
            requested = (int(min_mhz), int(max_mhz))
            wrote = write_str(self._level, "manual") and all(
                write_str(self._od, cmd)
                for cmd in sclk_commands(*requested)
            )
            if wrote and read_str(self._level) == "manual" and self.get() == requested:
                self._record("manual", requested, True)
                return True
            reason = "write_failed" if not wrote else "readback_mismatch"
        except Exception as exc:  # noqa: BLE001
            requested = (min_mhz, max_mhz)
            reason = type(exc).__name__
        if not self._restore(previous_level, previous_window):
            reason = f"{reason}_rollback_failed"
        self._record("manual", requested, False, reason)
        return False

    def _restore(self, level, window):
        if level == "manual" and window is not None:
            restored = write_str(self._level, "manual") and all(
                write_str(self._od, cmd) for cmd in sclk_commands(*window)
            )
            if restored and read_str(self._level) == "manual" and self.get() == window:
                return True
        elif level is not None:
            reset = write_str(self._od, "r")
            restored_window = reset
            if reset and window is not None and self.get() != window:
                restored_window = write_str(self._level, "manual") and all(
                    write_str(self._od, cmd) for cmd in sclk_commands(*window)
                ) and self.get() == window
            restored_level = write_str(self._level, level)
            if (
                restored_window
                and restored_level
                and read_str(self._level) == level
                and (window is None or self.get() == window)
            ):
                return True
        reset = write_str(self._od, "r")
        released = write_str(self._level, "auto")
        return (
            reset
            and released
            and read_str(self._level) == "auto"
            and self.get() == self.get_range()
        )

    def set_auto(self):
        if not self.supported:
            self._record("auto", None, False, "unsupported")
            return False
        try:
            target = self.get_range()
            reset = write_str(self._od, "r")
            released = write_str(self._level, "auto")
            applied = self.get()
            ok = (
                target is not None
                and reset
                and released
                and read_str(self._level) == "auto"
                and applied == target
            )
            self._record("auto", target, ok,
                         "" if ok else (
                             "reset_failed" if not reset else (
                                 "write_failed" if not released else (
                                     "readback_mismatch"
                                     if read_str(self._level) != "auto"
                                     else "reset_mismatch"
                                 )
                             )
                         ))
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
        readable = all(
            path is not None and read_int(path) is not None
            for path in (self._min, self._max, self._rpn, self._rp0)
        )
        writable = all(
            path is not None and os.access(path, os.W_OK)
            for path in (self._min, self._max)
        )
        return readable and writable

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

    def capture_state(self):
        window = self.get()
        return {"window": window} if window is not None else None

    def restore_state(self, state):
        if not isinstance(state, dict):
            return False
        window = state.get("window")
        if not isinstance(window, (list, tuple)) or len(window) != 2:
            return False
        return self.set(int(window[0]), int(window[1])) and self.get() == tuple(window)

    def set(self, min_mhz, max_mhz):
        if not self.supported:
            self._record("manual", (min_mhz, max_mhz), False, "unsupported")
            return False
        lo, hi = int(min_mhz), int(max_mhz)
        try:
            snapshot = self.get()
            if snapshot is None:
                self._record("manual", (lo, hi), False, "baseline_unavailable")
                return False
            wrote = self._write_window(lo, hi, snapshot)
            ok = wrote and self.get() == (lo, hi)
            if not ok:
                current = self.get()
                restored = current is not None and self._write_window(
                    snapshot[0], snapshot[1], current
                ) and self.get() == snapshot
                reason = "write_failed" if not wrote else "readback_mismatch"
                if not restored:
                    reason = f"{reason}_rollback_failed"
                self._record("manual", (lo, hi), False, reason)
                return False
            self._record("manual", (lo, hi), ok,
                         "" if ok else "readback_mismatch")
            return ok
        except Exception as exc:  # noqa: BLE001
            self._record("manual", (lo, hi), False, type(exc).__name__)
            return False

    def _write_window(self, lo, hi, current):
        writes = (
            ((self._max, hi), (self._min, lo))
            if lo > current[1]
            else ((self._min, lo), (self._max, hi))
        )
        return all(write_str(path, value) for path, value in writes)

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
        self._min = self._max = self._rpn = self._rp0 = None
        for maxp in sorted(glob.glob(os.path.join(root, _DRM, "card[0-9]*", "gt_max_freq_mhz"))):
            d = os.path.dirname(maxp)
            self._min = os.path.join(d, "gt_min_freq_mhz")
            self._max = maxp
            self._rpn = os.path.join(d, "gt_RPn_freq_mhz")
            self._rp0 = os.path.join(d, "gt_RP0_freq_mhz")
            if self.supported:
                break


class XeGpuClock(_FreqPairClock):
    """xe (Lunar Lake / MSI Claw): card*/device/tile*/gt0/freq0 frequency nodes.

    Only gt0 is eligible because gt1 may be a media GT rather than the render GPU.
    """

    backend = "xe"

    def __init__(self, root="/"):
        self._last_operation = None
        self._min = self._max = self._rpn = self._rp0 = None
        pattern = os.path.join(
            root, _DRM, "card[0-9]*", "device", "tile*", "gt0", "freq0", "max_freq"
        )
        for maxp in sorted(glob.glob(pattern)):
            d = os.path.dirname(maxp)
            self._min = os.path.join(d, "min_freq")
            self._max = maxp
            self._rpn = os.path.join(d, "rpn_freq")
            self._rp0 = os.path.join(d, "rp0_freq")
            if self.supported:
                break


class DevfreqGpuClock(_GpuDiagnostics):
    """ARM GPUs (Adreno, Mali): /sys/class/devfreq/<addr>.gpu, frequencies in Hz.

    Only the devfreq node named after the GPU is eligible; storage and bus
    controllers share the class.
    """

    backend = "devfreq"
    _AUTO_GOVERNOR = "simple_ondemand"

    def __init__(self, root="/"):
        self._last_operation = None
        self._dir = None
        for path in sorted(glob.glob(os.path.join(root, "sys/class/devfreq", "*.gpu"))):
            if self._table_at(path):
                self._dir = path
                break

    @staticmethod
    def _table_at(path):
        text = read_str(os.path.join(path, "available_frequencies")) or ""
        return tuple(sorted({int(item) for item in text.split() if item.isdigit()}))

    def _node(self, name):
        return os.path.join(self._dir, name)

    @property
    def supported(self):
        if self._dir is None or not self._table_at(self._dir):
            return False
        return all(
            read_int(self._node(name)) is not None and os.access(self._node(name), os.W_OK)
            for name in ("min_freq", "max_freq")
        )

    def _table(self):
        return self._table_at(self._dir) if self._dir is not None else ()

    def _window_hz(self):
        lo, hi = read_int(self._node("min_freq")), read_int(self._node("max_freq"))
        return (lo, hi) if lo is not None and hi is not None else None

    def levels(self):
        return [value // 1_000_000 for value in self._table()] if self.supported else None

    def get_range(self):
        table = self._table() if self.supported else ()
        return (table[0] // 1_000_000, table[-1] // 1_000_000) if table else None

    def get(self):
        if not self.supported:
            return None
        window = self._window_hz()
        return (window[0] // 1_000_000, window[1] // 1_000_000) if window else None

    def _snap(self, min_mhz, max_mhz):
        table = self._table()
        lo_hz, hi_hz = int(min_mhz) * 1_000_000, int(max_mhz) * 1_000_000
        hi = max((value for value in table if value <= hi_hz), default=table[0])
        lo = min((value for value in table if value >= lo_hz), default=table[-1])
        return min(lo, hi), hi

    def _write_window(self, lo, hi):
        current = self._window_hz()
        if current is None:
            return False
        writes = (
            (("max_freq", hi), ("min_freq", lo))
            if lo > current[1]
            else (("min_freq", lo), ("max_freq", hi))
        )
        return all(write_str(self._node(name), value) for name, value in writes)

    def _governor(self):
        return read_str(self._node("governor"))

    def capture_state(self):
        window = self._window_hz() if self.supported else None
        if window is None:
            return None
        return {"window_hz": list(window), "governor": self._governor()}

    def restore_state(self, state):
        if not isinstance(state, dict) or not self.supported:
            return False
        window = state.get("window_hz")
        if not isinstance(window, (list, tuple)) or len(window) != 2:
            return False
        governor = state.get("governor")
        if isinstance(governor, str) and governor and governor != self._governor():
            write_str(self._node("governor"), governor)
        target = (int(window[0]), int(window[1]))
        return self._write_window(*target) and self._window_hz() == target

    def set(self, min_mhz, max_mhz):
        if not self.supported:
            self._record("manual", (min_mhz, max_mhz), False, "unsupported")
            return False
        try:
            snapshot = self._window_hz()
            if snapshot is None:
                self._record("manual", (min_mhz, max_mhz), False, "baseline_unavailable")
                return False
            target = self._snap(min_mhz, max_mhz)
            wrote = self._write_window(*target)
            if wrote and self._window_hz() == target:
                self._record("manual", (min_mhz, max_mhz), True)
                return True
            restored = self._write_window(*snapshot) and self._window_hz() == snapshot
            reason = "write_failed" if not wrote else "readback_mismatch"
            if not restored:
                reason = f"{reason}_rollback_failed"
            self._record("manual", (min_mhz, max_mhz), False, reason)
            return False
        except Exception as exc:  # noqa: BLE001
            self._record("manual", (min_mhz, max_mhz), False, type(exc).__name__)
            return False

    def set_auto(self):
        rng = self.get_range()
        if not rng:
            self._record("auto", None, False, "range_unavailable")
            return False
        if self._governor() != self._AUTO_GOVERNOR:
            write_str(self._node("governor"), self._AUTO_GOVERNOR)
        ok = self.set(*rng)
        operation = getattr(self, "_last_operation", None)
        if operation is not None:
            operation["action"] = "auto"
        return ok


def select_gpu_clock(device, root="/"):
    """AMD → amdgpu OverDrive; Intel → xe (newer) then i915; else Null."""
    if getattr(device, "arch", "x86") == "arm":
        order = (DevfreqGpuClock,)
    elif getattr(device, "vendor", "amd") == "intel":
        order = (XeGpuClock, IntelGpuClock)
    else:
        order = (AmdGpuClock,)
    selection = []
    for cls in order:
        backend = cls(root)
        supported = bool(backend.supported)
        hardware_range = backend.get_range() if supported else None
        applied = backend.get() if supported else None
        selection.append({
            "backend": backend.backend,
            "supported": supported,
            "range_available": hardware_range is not None,
            "applied_available": applied is not None,
            "reason": "selected" if supported else "incomplete_or_unwritable",
        })
        if supported:
            backend._selection = selection
            return backend
    backend = NullGpuClock()
    backend._selection = selection
    return backend
