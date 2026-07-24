"""OneXPlayer OneXFly Apex fan backend: raw EC I/O via ec_sys debugfs.

On SteamOS the Valve kernel ships the ``oxpec`` driver but WITHOUT the Apex in its
DMI table (the entry is upstream and backported to 6.18.y/6.19.y, newer than the
current SteamOS kernel), so no hwmon fan node exists and fan control/monitoring is
impossible through the normal path. On Bazzite the newer kernel has it and control
works.

Until SteamOS rebases its kernel we drive the fan ourselves through the Embedded
Controller, using the register map the upstream driver documents for the
``oxp_fly`` board (same as the OneXFly F1):

  * ``0x4A`` mode: 0x00 firmware/auto, 0x01 manual
  * ``0x4B`` duty: PWM 0-255 (raw, no scaling on oxp_fly)
  * ``0x76``/``0x77`` RPM: 16-bit big-endian (read-only)

Access goes through ``ec_sys`` debugfs (``/sys/kernel/debug/ec/ec0/io``), where the
byte offset IS the EC register and every access is serialised by the kernel's ACPI
EC lock, which is safer than a raw ``/dev/port`` handshake. Writing needs ec_sys
loaded with ``write_support=1``; if that isn't available on the running kernel the
backend degrades honestly (control is refused, not reported as working).

Opt-in / experimental: gated behind the same toggle as the Legion Go S. Detection
is DMI-only (no EC I/O at construction), and this backend stands down the moment a
kernel exposes the real oxpec hwmon node, so the generic pwm path then takes over.
"""

import glob
import os
import threading
from typing import Callable, Optional

from fans.control import _interp, _read
from fans.software_loop import SoftwareLoopBackend

# EC register map (oxp_fly board — source: drivers/platform/x86/oxpec.c).
REG_MODE = 0x4A
REG_DUTY = 0x4B
REG_RPM = 0x76  # 16-bit big-endian across 0x76 (high) and 0x77 (low)
MODE_AUTO = 0x00
MODE_MANUAL = 0x01

# Above this temperature the curve is ignored and the fan forced to full duty — a
# bad or lazy curve must never leave the fan slow while hot (mirrors the Go S guard).
_APEX_TEMP_GUARD_C = 90
_RELEASE_CONFIRM_RETRIES = 3

_DMI_MATCH_APEX = ("ONEXPLAYER APEX",)
# oxpec hwmon chip names — when one appears the kernel driver owns the fan and this
# raw-EC backend must stand down (generic pwm handles it).
_OXP_HWMON_NAMES = ("oxp_ec", "oxpec", "oxp-sensors")

_DEBUGFS_IO = "sys/kernel/debug/ec/ec0/io"
_WRITE_PARAM = "sys/module/ec_sys/parameters/write_support"
_MODPROBE_CONF = "etc/modprobe.d/panel-de-control-apex-ec.conf"
_CONF_BODY = (
    "# Panel de Control: EC fan control for the OneXPlayer Apex (opt-in)\n"
    "options ec_sys write_support=1\n"
)


def oxpec_hwmon_present(root: str = "/") -> bool:
    """True when the kernel exposes the oxpec hwmon fan node (pwm or fan input). When
    it does, the real driver owns the fan and the raw-EC path stands down — and the
    'kernel doesn't have the driver yet' UI note no longer applies."""
    for d in glob.glob(os.path.join(root, "sys/class/hwmon/hwmon*")):
        if (_read(os.path.join(d, "name")) or "") in _OXP_HWMON_NAMES:
            if os.path.exists(os.path.join(d, "pwm1")) or \
                    os.path.exists(os.path.join(d, "fan1_input")):
                return True
    return False


class _EcSysIO:
    """EC access via ec_sys debugfs. The byte offset is the EC register; the kernel
    serialises each access under the ACPI EC lock. fd is opened lazily (only on a
    real device, first access) and every op is guarded — never raises."""

    def __init__(self, root: str = "/") -> None:
        self._path = os.path.join(root, _DEBUGFS_IO)
        self._fd: Optional[int] = None
        self._lock = threading.Lock()

    def _open(self) -> None:
        if self._fd is None:
            self._fd = os.open(self._path, os.O_RDWR)

    def read(self, addr: int) -> Optional[int]:
        with self._lock:
            try:
                self._open()
                return os.pread(self._fd, 1, addr)[0]
            except OSError:
                return None

    def write(self, addr: int, val: int) -> bool:
        with self._lock:
            try:
                self._open()
                os.pwrite(self._fd, bytes([val & 0xFF]), addr)
                return True
            except OSError:
                return False  # e.g. ec_sys without write_support → EINVAL


def _ensure_ec_sys_write() -> None:
    """Best-effort: make ec_sys expose the EC with write support. Persist the option
    for reboots, flip the runtime param if the module is already loaded, and modprobe
    it (loads if absent). Never raises; a kernel without ec_sys/write support simply
    leaves the EC unwritable and the caller degrades honestly."""
    try:
        conf = os.path.join("/", _MODPROBE_CONF)
        if not os.path.exists(conf):
            with open(conf, "w") as f:
                f.write(_CONF_BODY)
    except OSError:
        pass
    # If already loaded, try to flip the runtime parameter (bool module params are
    # commonly writable via sysfs).
    try:
        param = os.path.join("/", _WRITE_PARAM)
        if os.path.exists(param) and (_read(param) or "").strip() in ("N", "0"):
            with open(param, "w") as f:
                f.write("Y")
    except OSError:
        pass
    try:
        import subprocess

        from controllers.detect import clean_env, resolve_bin
        subprocess.run([resolve_bin("modprobe"), "ec_sys", "write_support=1"],
                       check=False, capture_output=True, timeout=5, env=clean_env())
    except Exception:  # noqa: BLE001
        pass


class OxpEcFanBackend(SoftwareLoopBackend):
    """OneXPlayer Apex EC fan control (opt-in, experimental). Duty-based (0x4B), with
    manual mode asserted at 0x4A. Confirmed by register readback (RPM does not
    reliably track a duty on these fans), with a high-temp guardian on top."""

    name = "oxp-apex-ec"
    min_rpm = 0
    max_rpm = 255  # the "target" IS the duty (0–255)

    def __init__(self, temp_fn: Optional[Callable[[], Optional[float]]] = None,
                 root: str = "/", ec=None) -> None:
        self._ec = ec or _EcSysIO(root)
        super().__init__(temp_fn=temp_fn, root=root)
        self._dmi_ok = self._dmi_matches()

    def _find_chip(self) -> Optional[str]:
        return None  # no hwmon node — support is DMI-based (see `supported`)

    @property
    def supported(self) -> bool:
        # Stand down if the kernel already exposes the oxpec hwmon fan node: the
        # generic pwm backend owns it then, so we never fight the real driver.
        return self._dmi_ok and not self._hwmon_fan_present()

    def _dmi_matches(self) -> bool:
        dmi = os.path.join(self._root, "sys/class/dmi/id")
        text = ((_read(os.path.join(dmi, "board_name")) or "") + " "
                + (_read(os.path.join(dmi, "product_name")) or "")).upper()
        return any(tok in text for tok in _DMI_MATCH_APEX)

    def _hwmon_fan_present(self) -> bool:
        return oxpec_hwmon_present(self._root)

    def _duty_to_target(self, duty: int) -> int:
        return max(0, min(255, int(duty)))

    def target_for_temp(self, temp: Optional[float]) -> Optional[int]:
        """Curve → duty (0–255). Duty 0 is a valid quiet point (fan off but still in
        manual mode — NOT a firmware release, which goes through the mode register).
        Past the hard temp limit, force full duty regardless of the curve. None
        (writes nothing) when not driving."""
        if self._points is None or temp is None:
            return None
        if temp >= _APEX_TEMP_GUARD_C:
            return 255
        return self._duty_to_target(_interp(self._points, temp))

    def _before_drive(self) -> bool:
        # Only touch the module on a real device; the probe (a benign same-value
        # write) tells us honestly whether the EC is writable on this kernel.
        if self._root == "/":
            _ensure_ec_sys_write()
        cur = self._ec.read(REG_MODE)
        if cur is None:
            return False
        return self._ec.write(REG_MODE, cur)

    def _write_target(self, duty: int) -> bool:
        duty = max(0, min(255, int(duty)))
        # Assert manual mode BEFORE the duty (the EC only honours 0x4B in manual), then
        # confirm both by readback — a write returning ok is not proof the EC took it.
        if self._ec.read(REG_MODE) != MODE_MANUAL:
            self._ec.write(REG_MODE, MODE_MANUAL)
        mode_ok = self._ec.read(REG_MODE) == MODE_MANUAL
        self._ec.write(REG_DUTY, duty)
        duty_ok = self._ec.read(REG_DUTY) == duty
        return mode_ok and duty_ok

    def _release(self) -> bool:
        # Hand the fan back to firmware by clearing the mode register. Confirm by
        # readback; retry so a transient failure self-heals. Auto mode is a clean
        # handback (no dead zone), so no fallback target is needed.
        for _ in range(_RELEASE_CONFIRM_RETRIES):
            self._ec.write(REG_MODE, MODE_AUTO)
            if self._ec.read(REG_MODE) == MODE_AUTO:
                return True
        return False

    def _read_rpm(self) -> Optional[int]:
        hi = self._ec.read(REG_RPM)
        lo = self._ec.read(REG_RPM + 1)
        if hi is None or lo is None:
            return None  # unreadable != a fake 0
        return (hi << 8) | lo

    def read_state(self) -> dict:
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}
        rpm = self._read_rpm()
        mode = self._ec.read(REG_MODE)
        # Ground truth from the mode register; fall back to our own drive state only
        # when the register is unreadable (ec_sys not loaded yet).
        if mode is not None:
            manual = mode == MODE_MANUAL
        else:
            manual = self._points is not None and self._drive_ok
        return {"supported": True, "source": self.name, "pwm_max": 255,
                "fans": [{"key": "fan", "enable": 1 if manual else 2,
                          "rpm": rpm, "points": []}]}
