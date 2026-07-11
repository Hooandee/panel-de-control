import os
import re
import shutil
import subprocess

from tdp.backend import TDPBackend
from tdp.types import TdpLimits, TdpResult

# The sustained (STAPM) limit line of `ryzenadj -i`.
_STAPM_RE = re.compile(r"STAPM LIMIT\s*\|\s*([\d.]+)", re.IGNORECASE)


def _parse_stapm(out: str) -> int | None:
    m = _STAPM_RE.search(out)
    if not m:
        return None
    try:
        return round(float(m.group(1)))
    except ValueError:
        return None


def _default_resolve():
    found = shutil.which("ryzenadj")
    if found:
        return found
    bundled = os.path.join(os.path.dirname(__file__), "..", "..", "bin", "ryzenadj")
    bundled = os.path.abspath(bundled)
    return bundled if os.path.exists(bundled) else None


def _clean_env():
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = ""
    return env


class RyzenadjBackend(TDPBackend):
    """Generic AMD fallback via the ryzenadj binary. Never raises."""

    name = "ryzenadj"
    blocking = True

    def __init__(self, fallback: TdpLimits, resolve=_default_resolve, runner=subprocess.run,
                 write_max: int | None = None):
        self._fallback = fallback
        # get_limits() reports the base policy; writes clamp to the device's absolute
        # ceiling (raised to cooler_max when a device has an external cooler, so the
        # Ajustes opt-in can actually reach the chip). main._limits() still gates the
        # effective policy, so a value above the base only arrives when the user opts in.
        self._write_limits = fallback.with_cooler(write_max) if write_max else fallback
        self._runner = runner
        self._bin = resolve()
        self.supported = self._bin is not None

    def get_limits(self) -> TdpLimits:
        return self._fallback

    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        if not self.supported:
            return TdpResult(watts, None, False, "ryzenadj binary not found")
        target = self._write_limits.clamp(watts)
        mw = str(target * 1000)
        argv = [
            self._bin,
            "--stapm-limit", mw,
            "--fast-limit", mw,
            "--slow-limit", mw,
            "--tctl-temp", "90",
        ]
        try:
            self._runner(argv, capture_output=True, text=True, timeout=5, env=_clean_env())
        except (OSError, subprocess.SubprocessError) as e:
            return TdpResult(watts, None, False, f"ryzenadj failed: {e}")
        applied = self.read_applied()
        ok = applied is not None
        return TdpResult(watts, applied, ok, "" if ok else "could not read back ryzenadj limits")

    def read_applied(self) -> int | None:
        if not self.supported:
            return None
        try:
            res = self._runner(
                [self._bin, "-i"],
                capture_output=True,
                text=True,
                timeout=5,
                env=_clean_env(),
            )
        except (OSError, subprocess.SubprocessError):
            return None
        out = getattr(res, "stdout", "") or ""
        return _parse_stapm(out)
