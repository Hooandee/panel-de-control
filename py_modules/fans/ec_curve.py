"""Read-only firmware fan-curve reader for the MSI Claw 8 AI+.

The msi_wmi_platform driver exposes RPM only (no writable pwm) on the current
kernel, so the write backend degrades to unsupported. The firmware's *active*
fan curve, however, is legible in the Embedded Controller RAM: 6 CPU points with
temperatures at ``0x6A`` and duty percentages at ``0x73`` (hex→decimal, direct).

Reading is done via ``ec_sys`` debugfs (``/sys/kernel/debug/ec/ec0/io``) with a
raw ``/dev/port`` handshake (ACPI EC ports 0x62/0x66) as a fallback. Only reads —
``ec_sys`` is loaded WITHOUT ``write_support`` and nothing is ever written back.

The curve is static firmware config, so the reader caches it after the first
successful read. Honest degradation: any unreadable / implausible dump yields
``None`` (never a fabricated curve).
"""

import os
import time
from typing import Callable, Optional

_POINTS = 6
CPU_TEMP_OFFSET = 0x6A
CPU_PCT_OFFSET = 0x73

_DEBUGFS_IO = "sys/kernel/debug/ec/ec0/io"
_EC_SIZE = 256

# ACPI EC I/O ports (standard command/data pair) for the /dev/port fallback.
_EC_DATA = 0x62
_EC_CMD = 0x66
_EC_CMD_READ = 0x80
# Status register bits (read at the command port).
_EC_IBF = 0x02  # input buffer full — wait until clear before writing
_EC_OBF = 0x01  # output buffer full — wait until set before reading


def parse_curve(data) -> Optional[list[tuple[int, int]]]:
    """Parse the 6-point CPU fan curve from an EC dump. Pure; never raises.

    Returns ``[(temp_c, pct), …]`` or ``None`` when the bytes don't form a
    plausible curve (short buffer, decreasing temps, out-of-range temps/pct, or
    an all-zero blank read).
    """
    if not data or len(data) < CPU_PCT_OFFSET + _POINTS:
        return None

    temps = list(data[CPU_TEMP_OFFSET:CPU_TEMP_OFFSET + _POINTS])
    pcts = list(data[CPU_PCT_OFFSET:CPU_PCT_OFFSET + _POINTS])

    if not any(temps):
        return None  # all-zero temps = blank/misaligned read, not a curve
    if any(t > 110 for t in temps):
        return None
    if any(p > 100 for p in pcts):
        return None
    if any(b < a for a, b in zip(temps, temps[1:])):
        return None  # temps must be non-decreasing
    if any(b < a for a, b in zip(pcts, pcts[1:])):
        return None  # duty must rise with temp (firmware curve invariant)

    return list(zip(temps, pcts))


def _ensure_ec_sys() -> None:
    """Load the ec_sys module (read-only) so debugfs exposes the EC. Never raises.

    Decky's PyInstaller-frozen loader hands children an empty PATH + a poisoned
    LD_LIBRARY_PATH, so a bare ``modprobe`` silently fails — resolve to an
    absolute path + clean_env (same fix as the MSI write backend).
    """
    try:
        import subprocess

        from controllers.detect import clean_env, resolve_bin
        subprocess.run([resolve_bin("modprobe"), "ec_sys"],
                       check=False, capture_output=True, timeout=5, env=clean_env())
    except Exception:  # noqa: BLE001
        pass


def _read_debugfs(root: str) -> Optional[bytes]:
    path = os.path.join(root, _DEBUGFS_IO)
    try:
        with open(path, "rb") as f:
            data = f.read(_EC_SIZE)
        return data if data else None
    except OSError:
        return None


def _wait(fd: int, mask: int, want: int, tries: int = 100) -> bool:
    """Poll the EC status register until (status & mask) == want. Never raises."""
    for _ in range(tries):
        try:
            status = os.pread(fd, 1, _EC_CMD)[0]
        except OSError:
            return False
        if (status & mask) == want:
            return True
        time.sleep(0.0001)
    return False


def _read_port(root: str) -> Optional[bytes]:
    """Read the EC via raw /dev/port using the ACPI 0x62/0x66 handshake.

    Fallback for when ec_sys/debugfs is unavailable. Reads only. Never raises.
    """
    if root != "/":
        return None  # raw ports are only meaningful on a real device
    fd = None
    try:
        fd = os.open("/dev/port", os.O_RDWR)
        out = bytearray(_EC_SIZE)
        for addr in range(_EC_SIZE):
            if not _wait(fd, _EC_IBF, 0):
                return None
            os.pwrite(fd, bytes([_EC_CMD_READ]), _EC_CMD)
            if not _wait(fd, _EC_IBF, 0):
                return None
            os.pwrite(fd, bytes([addr]), _EC_DATA)
            if not _wait(fd, _EC_OBF, _EC_OBF):
                return None
            out[addr] = os.pread(fd, 1, _EC_DATA)[0]
        return bytes(out)
    except OSError:
        return None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _default_source(root: str) -> Callable[[], Optional[bytes]]:
    def read() -> Optional[bytes]:
        _ensure_ec_sys()
        return _read_debugfs(root) or _read_port(root)
    return read


class EcFanCurveReader:
    """Reads + caches the MSI Claw firmware fan curve. Byte source is injectable."""

    def __init__(self, root: str = "/", read_bytes: Optional[Callable[[], Optional[bytes]]] = None) -> None:
        self._read_bytes = read_bytes or _default_source(root)
        self._cached: Optional[list[tuple[int, int]]] = None

    def read_curve(self) -> Optional[list[tuple[int, int]]]:
        """Return the parsed curve (cached) or ``None`` if unreadable. Never raises."""
        if self._cached is not None:
            return self._cached
        try:
            data = self._read_bytes()
        except Exception:  # noqa: BLE001
            return None
        curve = parse_curve(data)
        if curve is not None:
            self._cached = curve  # cache only success — transient failures retry
        return curve
