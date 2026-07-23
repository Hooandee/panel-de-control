import os
import subprocess

import acpi_call as _acpi_call
from tdp.backend import TDPBackend
from tdp.types import TdpLimits, TdpResult

# AMD power path via the ALIB ACPI method, invoked through the acpi_call kernel
# module (/proc/acpi/call). For platforms with no firmware-attributes ppt_* chip.
# Write-only: the applied limit is not read back.

_CALL_REL = "proc/acpi/call"
_METHOD = r"\_SB.ALIB"
_SET_FN = "0x1"

# ALIB parameter command ids (stable across AMD families). Only the power rails
# are driven; the skin/temp rails (0x2E/0x03) are not reliably honored on all
# families, so they are left to the firmware.
_STAPM_LIMIT = 0x05
_FAST_LIMIT = 0x06
_SLOW_LIMIT = 0x07

# First buffer byte = count of the bytes that follow it (cmd + LE32 value = 5).
_BUF_LEN = "05"

# Result substrings that mean the method was not applied.
_REJECT_TOKENS = ("error", "not found", "not called", "not supported", "not executed")


def _default_modprobe(module: str) -> None:
    # Decky's frozen (PyInstaller) loader hands children an empty PATH + a
    # poisoned LD_LIBRARY_PATH, so a bare "modprobe" silently no-ops. Resolve the
    # absolute binary and restore a sane env, as the other module loaders do.
    from controllers.detect import clean_env, resolve_bin
    subprocess.run([resolve_bin("modprobe"), module],
                   capture_output=True, timeout=5, env=clean_env())


def _buffer_arg(cmd_byte: int, value_mw: int) -> str:
    """Encode one ALIB set-parameter as an acpi_call buffer literal
    ``b`` + [length, cmd_byte, value little-endian(4)] as a hex string."""
    v = int(value_mw) & 0xFFFFFFFF
    body = bytes((cmd_byte, v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF))
    return "b" + _BUF_LEN + body.hex()


def _accepted(result) -> bool:
    # acpi_call echoes the method's return value, or an error string on failure.
    # Accept only a clean integer-zero return; an error token, empty output, or a
    # non-zero/unparseable value is treated as not applied.
    if not result:
        return False
    low = result.strip().strip("\x00").strip().lower()
    if not low or any(t in low for t in _REJECT_TOKENS):
        return False
    try:
        return int(low, 0) == 0
    except ValueError:
        return False


def _make_file_caller(path):
    # Route through the shared, lock-serialized acpi_call node so the ALIB (TDP) and
    # GZFD (fan) backends never tear each other's write-then-read response.
    def call(command: str):
        return _acpi_call.serialized_call(path, command)

    return call


class AlibBackend(TDPBackend):
    """Generic AMD TDP via the ALIB ACPI method through acpi_call. Never raises."""

    name = "acpi-alib"

    def __init__(self, fallback: TdpLimits, root: str = "/",
                 modprobe=_default_modprobe, caller=None, write_max: int | None = None) -> None:
        self._fallback = fallback
        self._write_limits = fallback.with_cooler(write_max)
        self._root = root
        self._call_path = os.path.join(root, _CALL_REL)
        self._modprobe = modprobe
        self._loaded = False
        # Construction runs on the asyncio loop (backend selection), so it must not
        # shell out: support is decided without loading the module — the call node
        # is already writable, or acpi_call is in the kernel's module index. The
        # modprobe is deferred to the first set_tdp, which runs off the loop.
        self._call = caller or _make_file_caller(self._call_path)
        self.supported = self._node_writable() or self._module_loadable()

    def _node_writable(self) -> bool:
        return os.path.exists(self._call_path) and os.access(self._call_path, os.W_OK)

    def _module_loadable(self) -> bool:
        try:
            release = os.uname().release
        except OSError:
            return False
        # usrmerge distros keep modules under /usr/lib/modules; older layouts under
        # /lib/modules. Scan both, line by line with an early break, so ALIB isn't
        # falsely skipped and a large index is never slurped whole.
        for base in ("usr/lib/modules", "lib/modules"):
            path = os.path.join(self._root, base, release, "modules.dep")
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if "acpi_call" in line:
                            return True
            except OSError:
                continue
        return False

    def _ensure_loaded(self) -> None:
        # Best-effort: load acpi_call so /proc/acpi/call exists. Fires from set_tdp
        # (off-loop). Mark "loaded" only once the node is actually writable, so a
        # transient or late-appearing failure self-heals on a later set_tdp instead
        # of latching the first failed attempt.
        if self._loaded:
            return
        if self._node_writable():
            self._loaded = True
            return
        try:
            self._modprobe("acpi_call")
        except Exception:  # noqa: BLE001
            return
        if self._node_writable():
            self._loaded = True

    def get_limits(self) -> TdpLimits:
        return self._fallback

    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        if not self.supported:
            return TdpResult(watts, None, False, "acpi_call ALIB interface unavailable")
        self._ensure_loaded()
        if not self._node_writable():
            return TdpResult(watts, None, False, "acpi_call ALIB interface unavailable")
        target = self._write_limits.clamp(watts, ac)
        mw = target * 1000
        # Short-term rails first so the sustained rail is never transiently highest.
        for cmd in (_FAST_LIMIT, _SLOW_LIMIT, _STAPM_LIMIT):
            result = self._call(f"{_METHOD} {_SET_FN} {_buffer_arg(cmd, mw)}")
            if not _accepted(result):
                return TdpResult(target, None, False, f"ALIB call not accepted: {result}")
        # The method does not report applied watts; applied stays None.
        return TdpResult(target, None, True, "")

    def read_applied(self) -> int | None:
        # Write-only path: the applied sustained limit is not exposed for reading.
        return None
