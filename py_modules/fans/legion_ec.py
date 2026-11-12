"""Legion Go 2 fan backend — raw EC I/O via /dev/port (no hwmon, no driver).

Mechanism transcribed from Rodpad/LeGo2-Fan-Control and confirmed read-only on a
real Legion Go 2 (.162): the RPM register tracks the live fan. We write a target
RPM to an override register and re-assert it (the EC reclaims the fan); releasing
= writing 0 to the override. Detected by DMI (8ASP2 / 83N0), since there is no
hwmon fan node on this device.

SAFETY: raw port I/O. The EC access layer is injectable (FakeEC in tests) so no
hardware is touched off-device. _PortEC opens /dev/port lazily — only ever on a
real matching device, and only on the first write/read.
"""

import os
import threading
from typing import Callable, Optional

from fans.control import _read, _interp
from fans.software_loop import SoftwareLoopBackend
import journal

# Number of write+readback attempts to confirm a release reached the EC.
_RELEASE_CONFIRM_RETRIES = 3

# EC register map (16-bit addresses; RPM/override are little-endian across addr,addr+1).
REG_RPM = 0xC6C0
REG_FACTORY = 0xC6C2
REG_OVERRIDE = 0xC6C8
REG_POWER_MODE = 0xC683

# Legion Go original (83E1): fan RPM is readable at EC 0xC664 (16-bit LE) even on
# kernels whose lenovo_wmi_other driver doesn't publish the hwmon fan node. Read-only.
REG_RPM_83E1 = 0xC664

# DMI tokens that identify the Legion Go 2 (product_version "Legion Go 8ASP2",
# product_name "83N0"). Matched case-insensitively against both fields.
_DMI_MATCH = ("8ASP2", "8AHP2", "83N0")


class _PortEC:
    """Real EC access via /dev/port using the SuperIO 0x4E/0x4F index/data
    protocol (exact sequence from LeGo2). Opens the fd lazily; never raises."""

    def __init__(self) -> None:
        self._fd: Optional[int] = None
        # The index/data protocol selects a GLOBAL address then reads/writes the data
        # window. A concurrent access (e.g. read_state's RPM read off the io lock, on
        # the loop thread) would re-select mid-sequence and land on the wrong register.
        # Serialise each select+access so every op is atomic.
        self._lock = threading.Lock()

    def _idx(self, reg: int, val: int) -> None:
        """Write one index-port pair: select index `reg` (at 0x4E), set `val` (at 0x4F)."""
        os.pwrite(self._fd, b"\x2e", 0x4E)
        os.pwrite(self._fd, bytes([reg]), 0x4F)
        os.pwrite(self._fd, b"\x2f", 0x4E)
        os.pwrite(self._fd, bytes([val & 0xFF]), 0x4F)

    def _select(self, addr: int) -> None:
        if self._fd is None:
            self._fd = os.open("/dev/port", os.O_RDWR)
        # Index 0x11 = addr high byte, 0x10 = addr low byte, 0x12 = data window.
        self._idx(0x11, (addr >> 8) & 0xFF)
        self._idx(0x10, addr & 0xFF)
        os.pwrite(self._fd, b"\x2e", 0x4E)
        os.pwrite(self._fd, b"\x12", 0x4F)
        os.pwrite(self._fd, b"\x2f", 0x4E)

    def read(self, addr: int) -> Optional[int]:
        with self._lock:
            try:
                self._select(addr)
                return os.pread(self._fd, 1, 0x4F)[0]
            except OSError:
                return None  # read failed != 0 RPM

    def write(self, addr: int, val: int) -> bool:
        with self._lock:
            try:
                self._select(addr)
                os.pwrite(self._fd, bytes([val & 0xFF]), 0x4F)
                return True
            except OSError as error:
                journal.write_failed(f"legion-ec:{addr:#04x}", val, error)
                return False


def _dmi_text(root: str, *fields: str) -> str:
    dmi = os.path.join(root, "sys/class/dmi/id")
    return " ".join(_read(os.path.join(dmi, field)) or "" for field in fields).upper()


def _read_le16(ec, addr: int) -> Optional[int]:
    """16-bit little-endian EC value across addr,addr+1. None if either read fails."""
    lo = ec.read(addr)
    hi = ec.read(addr + 1)
    if lo is None or hi is None:
        return None
    return (hi << 8) | lo


class LegionGo2FanBackend(SoftwareLoopBackend):
    """Legion Go 2: write a target RPM to the EC override register; release = 0."""

    name = "legion-go2-ec"
    min_rpm = 0
    max_rpm = 5000  # nominal; refine against the real fan's top RPM

    def __init__(self, temp_fn: Optional[Callable[[], Optional[float]]] = None,
                 root: str = "/", ec=None) -> None:
        self._ec = ec or _PortEC()
        super().__init__(temp_fn=temp_fn, root=root)
        self._dmi_ok = self._dmi_matches()

    def _find_chip(self) -> Optional[str]:
        return None  # no hwmon node — support is DMI-based (see `supported`)

    @property
    def supported(self) -> bool:
        return self._dmi_ok

    def _dmi_matches(self) -> bool:
        text = _dmi_text(self._root, "product_version", "product_name")
        return any(tok in text for tok in _DMI_MATCH)

    def _write_target(self, rpm: int) -> bool:
        # Two byte writes, either can fail — order them so a partial write never strands
        # the (0, MIN_SPIN) dead zone, and write the second only if the first (the safe
        # anchor) landed: releasing (0) writes LOW first (a lone low=0 leaves the old safe
        # high); driving writes HIGH first (a lone high >= 0x06 already reads >= 1536).
        # Truth is the readback.
        lo, hi = rpm & 0xFF, (rpm >> 8) & 0xFF
        if rpm == 0:
            if self._ec.write(REG_OVERRIDE, lo):
                self._ec.write(REG_OVERRIDE + 1, hi)
        else:
            if self._ec.write(REG_OVERRIDE + 1, hi):
                self._ec.write(REG_OVERRIDE, lo)
        return _read_le16(self._ec, REG_OVERRIDE) == rpm

    def _release(self) -> bool:
        # A write returning ok is not proof the EC took it: _write_target confirms 0
        # by readback. Retry so a transient single-byte failure self-heals.
        for _ in range(_RELEASE_CONFIRM_RETRIES):
            if self._write_target(0):
                return True
        # Could not confirm release — never leave a stale value in the stopped-but-
        # owned dead zone; drive the capped max (safe, spinning) instead.
        self._write_target(self.max_rpm)
        return False

    def _read_rpm(self) -> Optional[int]:
        return _read_le16(self._ec, REG_RPM)  # None when unreadable (not a fake 0)


# Legion Go S: RPM (0xC6C0) and override (0xC6C8) use the same SuperIO 0x4E map as
# the Go 2. Unofficial interface → gated behind an opt-in and wrapped in a safety
# harness (RPM cap + min-spin floor + high-temp guardian).
_DMI_MATCH_GOS = ("83N6", "83L3", "LEGION GO S")
# Cap the driven target below the firmware's own top (~4800 rpm observed): the curve's
# 100% maps here, so it can never be pushed to an out-of-range value.
_GOS_MAX_RPM = 4500
# The fan does not physically spin below this. A target in (0, MIN_SPIN) is the DANGER
# zone: the fan is stopped AND the firmware is locked out. So we only ever write 0
# (hand control back to the firmware) or a value in [MIN_SPIN, MAX_RPM]. This also
# makes a stuck override safe if the plugin ever dies — either firmware-controlled or
# genuinely cooling, never stopped-and-abandoned.
# 0x0600: the high byte of every driven target is >= 6, so even a low-byte write that
# fails leaves the override at high<<8 >= 1536 (never the dead zone).
_GOS_MIN_SPIN = 1536
# Above this temperature we ignore the user's curve and force full (capped) cooling —
# a bad curve must never leave the fan slow while hot.
_TEMP_GUARD_C = 90


class LegionGoSFanBackend(LegionGo2FanBackend):
    """Legion Go S EC fan control (opt-in, experimental). Same override mechanism as
    the Go 2, with an RPM ceiling, a min-spin floor (no dead zone), and a high-temp
    guardian layered on top."""

    name = "legion-go-s-ec"
    experimental = True
    max_rpm = _GOS_MAX_RPM

    @property
    def eligible(self) -> bool:
        return self.supported

    def _dmi_matches(self) -> bool:
        text = _dmi_text(self._root, "product_version", "product_name", "product_family")
        return any(tok in text for tok in _DMI_MATCH_GOS)

    def target_for_temp(self, temp: Optional[float]) -> Optional[int]:
        """Curve → a SAFE target. 0 when the curve wants no airflow (hand back to
        firmware); otherwise at least MIN_SPIN so a request never lands in the dead
        zone. Past the hard temp limit, force the capped max regardless of the curve.
        None (writes nothing) when not driving."""
        if self._points is None or temp is None:
            return None
        if temp >= _TEMP_GUARD_C:
            return self.max_rpm  # guardian
        duty = _interp(self._points, temp)
        if duty <= 0:
            return 0  # curve wants the fan off → release to firmware
        frac = min(255, duty) / 255.0
        return int(round(_GOS_MIN_SPIN + frac * (self.max_rpm - _GOS_MIN_SPIN)))


# Legion Go original: EC window from the DSDT (GZFD SFAN). SFNT = 1 makes the EC follow
# the 10-step fan table; a platform profile switch resets it to 0.
GO1_EC_BASE = 0xFE0B0000
GO1_SFNT = 0x30E
GO1_RPM = 0x38B
GO1_TABLE = 0x930
GO1_STEPS = 10
# The table is indexed by a board sensor far cooler than the APU, so the loop writes its
# duty to the cool steps and the hot steps keep the firmware minimums.
GO1_HOT_FLOOR = (None, None, None, None, None, 79, 87, 87, 100, 100)


class _MemEC:
    """Byte access to the EC window through /dev/mem. Never raises."""

    def __init__(self, base: int = GO1_EC_BASE, size: int = 0x1000) -> None:
        self._base = base
        self._size = size
        self._map = None
        self._lock = threading.Lock()
        self.error: Optional[str] = None

    def _ensure(self):
        if self._map is None:
            import mmap
            fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
            try:
                self._map = mmap.mmap(fd, self._size, mmap.MAP_SHARED,
                                      mmap.PROT_READ | mmap.PROT_WRITE, offset=self._base)
            finally:
                os.close(fd)
        return self._map

    def available(self) -> bool:
        with self._lock:
            try:
                self._ensure()
                return True
            except (OSError, ValueError) as error:
                self.error = type(error).__name__ + ":" + str(getattr(error, "errno", ""))
                return False

    def read(self, off: int) -> Optional[int]:
        with self._lock:
            try:
                return self._ensure()[off]
            except (OSError, ValueError, IndexError):
                return None

    def write(self, off: int, val: int) -> bool:
        with self._lock:
            try:
                self._ensure()[off] = val & 0xFF
                return True
            except (OSError, ValueError, IndexError) as error:
                journal.write_failed(f"legion-go-ec:{off:#05x}", val, error)
                return False


class LegionGoFanTableBackend(SoftwareLoopBackend):
    """Legion Go original: the loop writes the duty into the firmware table and keeps
    SFNT = 1; release = SFNT 0."""

    name = "legion-go-ec-table"
    resettable = False

    def __init__(self, temp_fn: Optional[Callable[[], Optional[float]]] = None,
                 root: str = "/", ec=None) -> None:
        super().__init__(temp_fn=temp_fn, root=root)
        self._dmi_ok = _dmi_text(root, "product_name").strip() == "83E1"
        self._ec = (ec or _MemEC()) if self._dmi_ok else None
        self._mapped = bool(self._ec is not None and self._ec.available())
        self._reasserts = 0
        self._last_duty: Optional[int] = None

    def _find_chip(self) -> Optional[str]:
        return None

    @property
    def supported(self) -> bool:
        return self._dmi_ok and self._mapped

    @staticmethod
    def table_for(duty: int) -> list:
        return [duty if floor is None else max(duty, floor) for floor in GO1_HOT_FLOOR]

    def target_for_temp(self, temp: Optional[float]) -> Optional[int]:
        if self._points is None or temp is None:
            return None
        if temp >= _TEMP_GUARD_C:
            return 100
        return max(0, min(100, round(_interp(self._points, temp) * 100 / 255)))

    def _read_table(self) -> list:
        return [self._ec.read(GO1_TABLE + i) for i in range(GO1_STEPS)]

    def _apply_once_locked(self) -> bool:
        duty = self.target_for_temp(self._temp_fn() if self._temp_fn else None)
        if duty is None:
            return False
        table = self.table_for(duty)
        sfnt = self._ec.read(GO1_SFNT)
        if sfnt == 1 and self._read_table() == table:
            self._drive_ok = True
            self._last_duty = duty
            return True
        if self._drive_ok and sfnt != 1:
            self._reasserts += 1
            diary = journal.active
            if diary is not None and self._reasserts & (self._reasserts - 1) == 0:
                diary.write("INFO", "fans", "table_reset", count=self._reasserts, sfnt=sfnt)
        # Table before SFNT so taking over never runs a half-written table.
        for i, pct in enumerate(table):
            self._ec.write(GO1_TABLE + i, pct)
        self._ec.write(GO1_SFNT, 1)
        self._drive_ok = self._ec.read(GO1_SFNT) == 1 and self._read_table() == table
        self._last_duty = duty if self._drive_ok else None
        return self._drive_ok

    def _write_target(self, rpm: int) -> bool:
        return False

    def _release(self) -> bool:
        self._last_duty = None
        for _ in range(_RELEASE_CONFIRM_RETRIES):
            if self._ec.write(GO1_SFNT, 0) and self._ec.read(GO1_SFNT) == 0:
                return True
        return False

    def _read_rpm(self) -> Optional[int]:
        return _read_le16(self._ec, GO1_RPM) if self._ec is not None else None

    def diagnostics(self) -> dict:
        if not self._dmi_ok:
            return {}
        if not self._mapped:
            return {"mapped": False, "error": getattr(self._ec, "error", None)}
        return {"mapped": True, "sfnt": self._ec.read(GO1_SFNT), "table": self._read_table(),
                "duty": self._last_duty, "reasserts": self._reasserts}


class LegionGoRpmReader:
    """Read-only fan RPM for the Legion Go original (83E1) over the EC. A monitor
    fallback for kernels where the hwmon fan node is absent. Never writes; never
    raises — returns None when the RPM can't be read (never a fake 0)."""

    def __init__(self, ec=None) -> None:
        self._ec = ec or _PortEC()

    def read_rpm(self) -> Optional[int]:
        return _read_le16(self._ec, REG_RPM_83E1)


def select_legion_rpm_reader(device, ec=None):
    """A read-only EC RPM reader for the Legion Go original, else None. Gated by model:
    the 0xC664 register is specific to the 83E1 EC map."""
    if getattr(device, "key", None) == "legion_go":
        return LegionGoRpmReader(ec=ec)
    return None
