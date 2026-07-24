"""Shared Embedded-Controller access over ``ec_sys`` debugfs.

The byte offset in ``/sys/kernel/debug/ec/ec0/io`` IS the EC register, and every
access is serialised by the kernel's ACPI EC lock (safer than a raw ``/dev/port``
handshake). Used by the raw-EC fan backends (MSI Claw, OneXPlayer Apex).

Writing needs ec_sys loaded with ``write_support=1``; that only takes effect on a
fresh load, so if ec_sys was already loaded read-only the node stays read-only and
``writable()`` reports it honestly rather than pretending to control.
"""

import os
from typing import Optional


class EcSys:
    """Real EC access via ec_sys debugfs. Loads the module with write_support=1
    once, opens the io file lazily, and never raises. Byte-addressed R/W."""

    _DEBUGFS_IO = "sys/kernel/debug/ec/ec0/io"

    def __init__(self, root: str = "/") -> None:
        self._root = root
        self._loaded = False

    def _path(self) -> str:
        return os.path.join(self._root, self._DEBUGFS_IO)

    def _ensure_loaded(self) -> None:
        # Load ec_sys with write_support at most once. Skip the subprocess entirely
        # when the io node is already writable (a prior load / session) so the common
        # path costs a single os.access stat. Latching after the attempt keeps repeated
        # writable()/supported reads from re-spawning a blocking subprocess (ec_sys
        # write availability is fixed for the boot — a read-only kernel stays honestly
        # unsupported).
        if self._loaded or self._root != "/":
            self._loaded = True
            return
        self._loaded = True
        if os.access(self._path(), os.W_OK):
            return
        try:
            import subprocess

            from controllers.detect import clean_env, resolve_bin
            subprocess.run([resolve_bin("modprobe"), "ec_sys", "write_support=1"],
                           check=False, capture_output=True, timeout=5, env=clean_env())
        except Exception:  # noqa: BLE001
            pass

    def writable(self) -> bool:
        """True only when the EC io file exists and is writable. Never raises."""
        self._ensure_loaded()
        return os.access(self._path(), os.W_OK)

    def read(self, addr: int) -> Optional[int]:
        self._ensure_loaded()
        try:
            with open(self._path(), "rb") as f:
                f.seek(addr)
                b = f.read(1)
            return b[0] if b else None
        except OSError:
            return None  # honest: read failed, value unknown

    def write(self, addr: int, val: int) -> bool:
        self._ensure_loaded()
        try:
            with open(self._path(), "r+b") as f:
                f.seek(addr)
                f.write(bytes([val & 0xFF]))
            return True
        except OSError:
            return False
