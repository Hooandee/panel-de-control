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
from typing import Callable, Optional

from fans.control import _read
from fans.software_loop import SoftwareLoopBackend

# EC register map (16-bit addresses; RPM/override are little-endian across addr,addr+1).
REG_RPM = 0xC6C0
REG_FACTORY = 0xC6C2
REG_OVERRIDE = 0xC6C8
REG_POWER_MODE = 0xC683

# DMI tokens that identify the Legion Go 2 (product_version "Legion Go 8ASP2",
# product_name "83N0"). Matched case-insensitively against both fields.
_DMI_MATCH = ("8ASP2", "8AHP2", "83N0")


class _PortEC:
    """Real EC access via /dev/port using the SuperIO 0x4E/0x4F index/data
    protocol (exact sequence from LeGo2). Opens the fd lazily; never raises."""

    def __init__(self) -> None:
        self._fd: Optional[int] = None

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
        try:
            self._select(addr)
            return os.pread(self._fd, 1, 0x4F)[0]
        except OSError:
            return None  # honest: read failed != 0 RPM

    def write(self, addr: int, val: int) -> bool:
        try:
            self._select(addr)
            os.pwrite(self._fd, bytes([val & 0xFF]), 0x4F)
            return True
        except OSError:
            return False


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
        dmi = os.path.join(self._root, "sys/class/dmi/id")
        text = ((_read(os.path.join(dmi, "product_version")) or "") + " "
                + (_read(os.path.join(dmi, "product_name")) or "")).upper()
        return any(tok in text for tok in _DMI_MATCH)

    def _write_target(self, rpm: int) -> bool:
        ok_lo = self._ec.write(REG_OVERRIDE, rpm & 0xFF)
        ok_hi = self._ec.write(REG_OVERRIDE + 1, (rpm >> 8) & 0xFF)
        return bool(ok_lo and ok_hi)

    def _release(self) -> bool:
        ok_lo = self._ec.write(REG_OVERRIDE, 0)
        ok_hi = self._ec.write(REG_OVERRIDE + 1, 0)
        return bool(ok_lo and ok_hi)

    def _read_rpm(self) -> Optional[int]:
        hi = self._ec.read(REG_RPM + 1)
        lo = self._ec.read(REG_RPM)
        if hi is None or lo is None:
            return None  # honest: EC read failed, RPM unknown (not 0)
        return (hi << 8) | lo
