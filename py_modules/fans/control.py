"""Fan-curve write backend for hwmon-based devices.

Currently supports the ASUS ``asus_custom_fan_curve`` hwmon chip found on
ROG Ally / ROG Xbox Ally X.  Other devices degrade to ``NullFanBackend``
(unsupported, read-only safe).

Safety guarantee: ``sanitize_curve`` ensures the last curve point always
reaches at least ``_SAFE_MAX_TEMP_FLOOR`` (≈30 % of 255 ≈ 76) so no manual
curve can leave a fan idle when the device is hot.
"""

import glob
import os
from typing import Optional

_HWMON = "sys/class/hwmon"
_CHIP_NAME = "asus_custom_fan_curve"

# Minimum PWM the last (hottest) curve point must reach.
# 76 ≈ 30 % of 255 — loud enough to protect the chip at max temp.
_SAFE_MAX_TEMP_FLOOR: int = 76

# Fan index mapping: friendly key → hwmon pwmM index.
_FAN_KEYS: dict[str, int] = {"cpu": 1, "gpu": 2}
_POINTS: int = 8


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _interp(points: list, temp: float, round_int: bool = True):
    """Linear-interpolated value of a (x, y) curve at *temp*; clamps ends.

    Used for both temp→pwm (round_int=True, integer pwm) and the suggestion's
    temp→duty% shaping (round_int=False, float).
    """
    pts = sorted((float(t), float(p)) for t, p in points)
    if not pts:
        return 0

    def out(v):
        return int(round(v)) if round_int else v

    if temp <= pts[0][0]:
        return out(pts[0][1])
    for (t0, p0), (t1, p1) in zip(pts, pts[1:]):
        if temp <= t1:
            if t1 == t0:
                return out(p1)
            frac = (temp - t0) / (t1 - t0)
            return out(p0 + frac * (p1 - p0))
    return out(pts[-1][1])


def sanitize_curve(
    points: list,
    pwm_max: int = 255,
    floor_pwm: int = 0,
    n_points: int = _POINTS,
) -> list[tuple[int, int]]:
    """Return a safe ``n_points`` ``[(temp, pwm), …]`` list suitable for writing.

    Rules applied in order:
    1. Truncate to n_points / pad by repeating the last point.
    2. Cast to int.
    3. Clamp temps to 0..100, pwm to ``[floor_pwm, pwm_max]``.
    4. Make temps non-decreasing (clamp each point's temp to >= the previous).
    5. Make pwm monotonically non-decreasing.
    6. Enforce ``_SAFE_MAX_TEMP_FLOOR`` on the LAST point only — lower points
       may remain quiet.

    Never raises.
    """
    if not points:
        points = [(0, 0)]

    # 1. Normalise length
    pts: list[tuple[int, int]] = [(int(t), int(p)) for t, p in points[:n_points]]
    while len(pts) < n_points:
        pts.append(pts[-1])

    # 2+3. Clamp
    pts = [(max(0, min(100, t)), max(floor_pwm, min(pwm_max, p))) for t, p in pts]

    # 4. Make temps non-decreasing
    result: list[tuple[int, int]] = [pts[0]]
    for t, p in pts[1:]:
        prev_t = result[-1][0]
        if t <= prev_t:
            t = prev_t  # keep equal (monotone, not strictly increasing)
        result.append((t, p))

    # 5. Make pwm monotonically non-decreasing
    final: list[tuple[int, int]] = [result[0]]
    for t, p in result[1:]:
        prev_p = final[-1][1]
        final.append((t, max(p, prev_p)))

    # 6. Enforce safe floor on last point only
    effective_floor = max(floor_pwm, _SAFE_MAX_TEMP_FLOOR)
    t_last, p_last = final[-1]
    if p_last < effective_floor:
        final[-1] = (t_last, effective_floor)

    return final


# ---------------------------------------------------------------------------
# I/O helpers (never raise)
# ---------------------------------------------------------------------------

def _read(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int(path: str) -> Optional[int]:
    v = _read(path)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _write(path: str, value: str) -> bool:
    try:
        with open(path, "w") as f:
            f.write(value)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Backend classes
# ---------------------------------------------------------------------------

class NullFanBackend:
    """Returned when no supported fan-control chip is found on this device."""

    supported: bool = False
    name: str = "null"

    def read_state(self) -> dict:
        return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}

    def set_curve(self, fan_key: str, points: list) -> dict:
        return {"ok": False, "detail": "fan control not supported on this device"}

    def set_auto(self, fan_key: Optional[str] = None) -> dict:
        return {"ok": False, "detail": "fan control not supported on this device"}

    def apply_curve_all(self, points: list) -> dict:
        return {"ok": False, "detail": "fan control not supported on this device"}

    def restore_auto(self) -> dict:
        return self.set_auto(None)


class HwmonCurveBackend:
    """Generic hwmon fan-curve backend for the firmware-curve-table family.

    These chips expose, per fan M (1=CPU, 2=GPU):
    - ``pwmM_auto_pointK_temp`` (°C, K=1..n_points)
    - ``pwmM_auto_pointK_pwm``  (raw 0..255, monotonically non-decreasing)
    - ``pwmM_enable``           (2 = firmware auto, 1 = use the written points)

    The firmware executes the written table autonomously — no software loop.
    Two members today: ``asus_custom_fan_curve`` (Ally, 8 points, free temps) and
    ``msi_wmi_platform`` (MSI Claw, 6 points, FIXED temps → the incoming curve is
    resampled at those anchors). All files are root:root 0644; the plugin is root.
    """

    def __init__(self, chip_name: str, n_points: int = _POINTS,
                 fixed_temps: Optional[tuple] = None, fan_keys: Optional[dict] = None,
                 root: str = "/") -> None:
        self.name = chip_name
        self._chip_name = chip_name
        self._n_points = n_points
        self._fixed_temps = tuple(fixed_temps) if fixed_temps else None
        self._fan_keys = fan_keys or _FAN_KEYS
        self._root = root
        self._dir: Optional[str] = self._find_chip()

    @property
    def supported(self) -> bool:
        return self._dir is not None

    def _find_chip(self) -> Optional[str]:
        pattern = os.path.join(self._root, _HWMON, "hwmon*")
        for d in sorted(glob.glob(pattern)):
            if _read(os.path.join(d, "name")) == self._chip_name:
                # Confirm at least one pwm point file is present
                if os.path.exists(os.path.join(d, "pwm1_auto_point1_pwm")):
                    return d
        return None

    def _writable_points(self, points: list) -> list:
        """Resolve the incoming canonical curve to this chip's writable points.

        Fixed-temp chips (MSI) resample the curve at their anchors; free-temp
        chips (ASUS) keep the curve's own temps. Both pass through the safety
        sanitize (monotonic + hot-point floor) at the chip's point count.
        """
        if self._fixed_temps:
            raw = [(t, _interp(points, t)) for t in self._fixed_temps]
            return sanitize_curve(raw, pwm_max=255, floor_pwm=0, n_points=len(self._fixed_temps))
        return sanitize_curve(points, pwm_max=255, floor_pwm=0, n_points=self._n_points)

    # --- public API -----------------------------------------------------------

    def read_state(self) -> dict:
        """Read current curve and enable state for all present fans. Never raises."""
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}

        fans = []
        for fan_key, fan_index in self._fan_keys.items():
            enable_path = os.path.join(self._dir, f"pwm{fan_index}_enable")
            if not os.path.exists(enable_path):
                continue  # this fan index not present on this chip
            enable = _read_int(enable_path)
            points = []
            for point in range(1, self._n_points + 1):
                temp = _read_int(os.path.join(self._dir, f"pwm{fan_index}_auto_point{point}_temp"))
                pwm = _read_int(os.path.join(self._dir, f"pwm{fan_index}_auto_point{point}_pwm"))
                points.append({"temp": temp, "pwm": pwm})
            fans.append({"key": fan_key, "enable": enable, "points": points})

        return {"supported": True, "source": self.name, "pwm_max": 255, "fans": fans}

    def set_curve(self, fan_key: str, points: list) -> dict:
        """Write a sanitized fan curve and switch the fan to manual mode. Never raises."""
        if not self.supported:
            return {"ok": False, "detail": f"{self._chip_name} chip not found"}

        fan_index = self._fan_keys.get(fan_key)
        if fan_index is None:
            return {"ok": False, "detail": f"unknown fan key: {fan_key!r}"}

        safe_points = self._writable_points(points)

        for point, (temp, pwm) in enumerate(safe_points, start=1):
            if not _write(os.path.join(self._dir, f"pwm{fan_index}_auto_point{point}_temp"), str(temp)):
                return {"ok": False, "detail": f"write failed: pwm{fan_index}_auto_point{point}_temp"}
            if not _write(os.path.join(self._dir, f"pwm{fan_index}_auto_point{point}_pwm"), str(pwm)):
                return {"ok": False, "detail": f"write failed: pwm{fan_index}_auto_point{point}_pwm"}

        if not _write(os.path.join(self._dir, f"pwm{fan_index}_enable"), "1"):
            return {"ok": False, "detail": f"write failed: pwm{fan_index}_enable"}

        # Read back point 1 to confirm the kernel accepted the write
        if _read_int(os.path.join(self._dir, f"pwm{fan_index}_auto_point1_pwm")) is None:
            return {"ok": False, "detail": "readback failed after write"}

        return {"ok": True, "detail": f"fan {fan_key} curve applied (manual mode)"}

    def apply_curve_all(self, points: list) -> dict:
        """Write the SAME curve to every fan present on the chip. Never raises."""
        if not self.supported:
            return {"ok": False, "detail": f"{self._chip_name} chip not found"}
        applied, failed = [], []
        for fan_key, fan_index in self._fan_keys.items():
            if not os.path.exists(os.path.join(self._dir, f"pwm{fan_index}_enable")):
                continue  # fan index not present on this chip
            result = self.set_curve(fan_key, points)
            (applied if result.get("ok") else failed).append(fan_key)
        if not applied and not failed:
            return {"ok": False, "detail": "no fans present"}
        if failed:
            return {"ok": False, "detail": f"curve write failed for: {failed}"}
        return {"ok": True, "detail": f"curve applied to {applied}"}

    def set_auto(self, fan_key: Optional[str] = None) -> dict:
        """Return the given fan (or all when None) to firmware auto (enable=2). Never raises."""
        if not self.supported:
            return {"ok": False, "detail": f"{self._chip_name} chip not found"}

        if fan_key is not None:
            fan_index = self._fan_keys.get(fan_key)
            if fan_index is None:
                return {"ok": False, "detail": f"unknown fan key: {fan_key!r}"}
            fans_to_restore = [(fan_key, fan_index)]
        else:
            fans_to_restore = list(self._fan_keys.items())

        failed = []
        for fan_key, fan_index in fans_to_restore:
            enable_path = os.path.join(self._dir, f"pwm{fan_index}_enable")
            if not _write(enable_path, "2"):
                failed.append(fan_key)

        if failed:
            return {"ok": False, "detail": f"enable=2 write failed for: {failed}"}
        return {"ok": True, "detail": "fan(s) returned to firmware auto"}

    def restore_auto(self) -> dict:
        """Fail-safe: restore ALL fans to firmware auto.  Called on plugin unload."""
        return self.set_auto(None)


class AsusFanCurveBackend(HwmonCurveBackend):
    """ROG Ally / ROG Xbox Ally X — ``asus_custom_fan_curve`` (8 points, free temps)."""

    def __init__(self, root: str = "/") -> None:
        super().__init__(_CHIP_NAME, n_points=_POINTS, fixed_temps=None, root=root)


# MSI Claw exposes 6 curve points at fixed temperature anchors (per hhd/adjustor).
_MSI_CHIP = "msi_wmi_platform"
_MSI_TEMPS = (0, 50, 60, 70, 80, 88)


class MsiFanCurveBackend(HwmonCurveBackend):
    """MSI Claw 8 AI+ — ``msi_wmi_platform`` hwmon (6 points, FIXED temp anchors).

    The driver historically doesn't autoload, so we modprobe it on a real device
    before discovery (skipped under a synthetic test root).
    """

    def __init__(self, root: str = "/") -> None:
        # Only shell out to modprobe on a real MSI device — the factory constructs
        # this candidate on every non-ASUS handheld, so guard by DMI vendor.
        if root == "/" and _is_msi_vendor(root):
            try:
                import subprocess
                # Decky's PyInstaller-frozen loader gives the child an empty PATH +
                # a poisoned LD_LIBRARY_PATH → a bare "modprobe" silently fails and
                # the msi_wmi_platform chip never appears. Resolve to an absolute
                # path + clean_env (same fix as fans/expose.py and software_loop).
                from controllers.detect import clean_env, resolve_bin
                subprocess.run([resolve_bin("modprobe"), "msi_wmi_platform"],
                               check=False, capture_output=True, timeout=5, env=clean_env())
            except Exception:  # noqa: BLE001
                pass
        super().__init__(_MSI_CHIP, n_points=6, fixed_temps=_MSI_TEMPS, root=root)


_LEGION_WMI_CHIP = "legion_wmi_fan"
_LEGION_WMI_TEMPS = (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)


class LegionWmiFanBackend(HwmonCurveBackend):
    """Legion Go ``legion_wmi_fan`` hwmon (10 points, fixed temp anchors, one fan).

    The kernel driver runs the written curve autonomously (no software loop),
    like the ASUS chip. Provided by the mainline lenovo/legion WMI fan driver;
    absent kernels degrade to the read-only monitor (NullFanBackend)."""

    def __init__(self, root: str = "/") -> None:
        super().__init__(_LEGION_WMI_CHIP, n_points=10, fixed_temps=_LEGION_WMI_TEMPS,
                         fan_keys={"fan": 1}, root=root)

    def set_curve(self, fan_key: str, points: list) -> dict:
        """Write the pwm points and switch to manual mode. This chip fixes the
        temp anchors and exposes no writable temp files, so only pwm is written."""
        if not self.supported:
            return {"ok": False, "detail": f"{self._chip_name} chip not found"}
        fan_index = self._fan_keys.get(fan_key)
        if fan_index is None:
            return {"ok": False, "detail": f"unknown fan key: {fan_key!r}"}

        for point, (_temp, pwm) in enumerate(self._writable_points(points), start=1):
            if not _write(os.path.join(self._dir, f"pwm{fan_index}_auto_point{point}_pwm"), str(pwm)):
                return {"ok": False, "detail": f"write failed: pwm{fan_index}_auto_point{point}_pwm"}

        if not _write(os.path.join(self._dir, f"pwm{fan_index}_enable"), "1"):
            return {"ok": False, "detail": f"write failed: pwm{fan_index}_enable"}
        if _read_int(os.path.join(self._dir, f"pwm{fan_index}_auto_point1_pwm")) is None:
            return {"ok": False, "detail": "readback failed after write"}
        return {"ok": True, "detail": f"fan {fan_key} curve applied (manual mode)"}


def _is_msi_vendor(root: str) -> bool:
    vendor = (_read(os.path.join(root, "sys/class/dmi/id/sys_vendor")) or "").lower()
    return "micro-star" in vendor or "msi" in vendor


def select_firmware_curve_reader(device, root: str = "/"):
    """Return a read-only firmware fan-curve reader, or None if this device has no
    legible firmware curve. Keeps the vendor test beside the write-backend selection.

    Only the MSI Claw applies today: its ``msi_wmi_platform`` driver is read-only
    RPM (no writable pwm), but the firmware's active curve is legible over the EC.
    """
    if _is_msi_vendor(root):
        from fans.ec_curve import EcFanCurveReader
        return EcFanCurveReader(root=root)
    return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def select_fan_backend(device, root: str = "/", temp_fn=None, ec=None, experimental=False):
    """Return the best available fan-control backend for this device.

    Chip/attr based (not device-name based) so it's robust across the matrix:
    1. ``asus_custom_fan_curve`` (ROG Ally family) — hardware curve table.
    2. ``msi_wmi_platform`` (MSI Claw) — hardware curve table (only when its
       kernel exposes a WRITABLE pwm point; read-only kernels fall through).
    3. ``legion_wmi_fan`` (Legion Go original) — hardware curve table, present
       only when the kernel ships the lenovo/legion WMI fan driver.
    3b. Legion Go original acpi_call→GZFD firmware curve — the fallback when that
       driver is absent but acpi_call is loadable (Bazzite/CachyOS); SteamOS lacks
       acpi_call → falls through to the read-only monitor.
    4. ``steamdeck_hwmon`` (Steam Deck) — software loop (needs ``temp_fn``).
    5. Legion Go 2 raw-EC software loop.
    6. Legion Go S raw-EC software loop — ONLY when ``experimental`` is on (its
       EC interface is unofficial; off = read-only monitor via NullFanBackend).
    7. ``NullFanBackend`` when nothing supported is found (read-only safety).

    MSI Claw EC 0x33 step control (``msi_ec.MsiEcFanBackend``) is intentionally
    NOT wired: driving the fan to its top step resets the device (the EC drops
    into a full-blast failsafe that ignores further writes), so the Claw stays
    on firmware auto until a safe ceiling is proven. ``ec`` stays for that
    backend's own tests.
    """
    for backend_cls in (AsusFanCurveBackend, MsiFanCurveBackend, LegionWmiFanBackend):
        backend = backend_cls(root=root)
        if backend.supported:
            return backend
    # 83E1 (Legion Go original) fallback: no in-kernel legion_wmi_fan driver, but
    # acpi_call is loadable (Bazzite/CachyOS) — drive the firmware curve via GZFD,
    # exactly as HHD does. Absent on SteamOS -> falls through to the read-only Null.
    if getattr(device, "key", None) == "legion_go":
        from fans.legion_acpi import LegionAcpiCallFanBackend
        lego = LegionAcpiCallFanBackend(root=root)
        if lego.supported:
            return lego
    # Software-loop backends (lazy import avoids a circular dependency).
    from fans.software_loop import SteamDeckFanBackend
    from fans.legion_ec import LegionGo2FanBackend
    for backend in (SteamDeckFanBackend(temp_fn=temp_fn, root=root),
                    LegionGo2FanBackend(temp_fn=temp_fn, root=root)):
        if backend.supported:
            return backend
    # Legion Go S EC control is opt-in (unofficial interface). When the toggle is
    # off it falls through to the read-only monitor below.
    if experimental:
        from fans.legion_ec import LegionGoSFanBackend
        gos = LegionGoSFanBackend(temp_fn=temp_fn, root=root)
        if gos.supported:
            return gos
    # Last resort for unrecognised hardware: the standard hwmon manual-PWM interface.
    from fans.generic_pwm import GenericPwmFanBackend
    generic = GenericPwmFanBackend(temp_fn=temp_fn, root=root)
    if generic.supported:
        return generic
    return NullFanBackend()
