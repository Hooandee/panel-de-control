import os
import re
import shutil
import subprocess

from tdp.backend import TDPBackend
from tdp.types import TdpLimits, TdpResult

# The sustained (STAPM) limit line of `ryzenadj -i`.
_STAPM_RE = re.compile(r"STAPM LIMIT\s*\|\s*([\d.]+)", re.IGNORECASE)

# Readback slack (W): the STAPM readback rounds, so treat a near-match as applied.
_READBACK_TOLERANCE_W = 2


def _unreadable(applied):
    # No STAPM limit to read back: absent (None) or a 0 that some APUs report even when
    # the write applied.
    return applied is None or applied == 0


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
        # Writes clamp to the absolute ceiling (cooler_max); get_limits keeps the base.
        self._write_limits = fallback.with_cooler(write_max)
        self._runner = runner
        self._bin = resolve()
        self.supported = self._bin is not None

    def get_limits(self) -> TdpLimits:
        return self._fallback

    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        if not self.supported:
            return TdpResult(watts, None, False, "ryzenadj binary not found")
        target = self._write_limits.clamp(watts)
        # amd_pmf (and the firmware on some Z2 handhelds) can silently clobber a single
        # write, so the limit "doesn't always apply". Write, read back, and re-assert
        # once. Then classify honestly:
        #   - reads back the target (±slack) -> applied, confirmed.
        #   - reads back a different real value -> the write was rejected/clamped -> fail
        #     and report the value it actually holds (never fake success).
        #   - can't read the limit at all (STAPM line absent or 0 -- a known quirk on
        #     some APUs where the write still applies) -> assume applied, unconfirmed;
        #     the re-assert is our best effort. Don't cry failure on a working device.
        applied = None
        for _ in range(2):
            try:
                self._apply(target)
            except (OSError, subprocess.SubprocessError) as e:
                return TdpResult(watts, None, False, f"ryzenadj failed: {e}")
            applied = self.read_applied()
            if _unreadable(applied):
                continue  # re-assert once, then treat as unconfirmed
            if abs(applied - target) <= _READBACK_TOLERANCE_W:
                return TdpResult(watts, applied, True, "")
        if _unreadable(applied):
            return TdpResult(watts, None, True, "applied (limit readback unavailable)")
        return TdpResult(watts, applied, False,
                         f"ryzenadj limit did not stick (wanted {target}, holds {applied})")

    def _apply(self, target: int) -> None:
        mw = str(target * 1000)
        argv = [
            self._bin,
            "--stapm-limit", mw,
            "--fast-limit", mw,
            "--slow-limit", mw,
            "--tctl-temp", "90",
        ]
        self._runner(argv, capture_output=True, text=True, timeout=5, env=_clean_env())

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
