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


def _matches(applied, target):
    return not _unreadable(applied) and abs(applied - target) <= _READBACK_TOLERANCE_W


def _gpd_detail(*, variant, primary_exit, exit_code, readback):
    return (
        f"gpd recovery variant={variant} primary_exit={int(primary_exit)} "
        f"exit={int(exit_code)} readback={readback}"
    )


def _parse_stapm(out: str) -> int | None:
    m = _STAPM_RE.search(out)
    if not m:
        return None
    try:
        return round(float(m.group(1)))
    except ValueError:
        return None


def _ensure_executable(path: str) -> None:
    """Make our bundled binary runnable. A plain zip extract (the self-updater) drops
    the exec bit, so it can land mode 0o644, and execve gives EACCES even as root when
    no exec bit is set. We own this file, so restore +x. Best-effort: never raise."""
    try:
        mode = os.stat(path).st_mode
        if mode & 0o111 != 0o111:
            os.chmod(path, mode | 0o111)
    except OSError:
        pass


def _default_resolve():
    found = shutil.which("ryzenadj")
    if found:
        return found
    bundled = os.path.join(os.path.dirname(__file__), "..", "..", "bin", "ryzenadj")
    bundled = os.path.abspath(bundled)
    if not os.path.exists(bundled):
        return None
    _ensure_executable(bundled)
    return bundled


def _clean_env():
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = ""
    return env


class RyzenadjBackend(TDPBackend):
    """Generic AMD fallback via the ryzenadj binary. Never raises."""

    name = "ryzenadj"
    blocking = True
    guard_interval_s = 15.0
    read_tolerance_w = _READBACK_TOLERANCE_W

    def __init__(self, fallback: TdpLimits, resolve=_default_resolve, runner=subprocess.run,
                 write_max: int | None = None, power_only_retry: bool = False):
        self._fallback = fallback
        # Writes clamp to the absolute ceiling (cooler_max); get_limits keeps the base.
        self._write_limits = fallback.with_cooler(write_max)
        self._runner = runner
        self._bin = resolve()
        self._power_only_retry = power_only_retry
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
                primary_exit = self._apply(target)
            except (OSError, subprocess.SubprocessError) as e:
                if self._power_only_retry:
                    return TdpResult(
                        watts, None, False,
                        f"ryzenadj primary failed ({type(e).__name__})",
                    )
                return TdpResult(watts, None, False, f"ryzenadj failed: {e}")
            if self._power_only_retry and primary_exit:
                return self._recover_gpd(watts, target, primary_exit)
            applied = self.read_applied()
            if _unreadable(applied):
                continue  # re-assert once, then treat as unconfirmed
            if _matches(applied, target):
                return TdpResult(watts, applied, True, "")
        if _unreadable(applied):
            return TdpResult(watts, None, True, "applied (limit readback unavailable)")
        return TdpResult(watts, applied, False,
                         f"ryzenadj limit did not stick (wanted {target}, holds {applied})")

    def _recover_gpd(self, watts: int, target: int, primary_exit: int) -> TdpResult:
        applied = self._read_applied(require_zero_exit=True)
        if _matches(applied, target):
            return TdpResult(
                watts,
                applied,
                True,
                _gpd_detail(
                    variant="primary",
                    primary_exit=primary_exit,
                    exit_code=primary_exit,
                    readback="confirmed",
                ),
            )
        try:
            fallback_exit = self._apply(target, include_temp=False)
        except (OSError, subprocess.SubprocessError) as e:
            return TdpResult(
                watts,
                applied,
                False,
                f"ryzenadj power-only failed ({type(e).__name__}) "
                f"primary_exit={int(primary_exit)}",
            )
        applied = self._read_applied(require_zero_exit=True)
        if _unreadable(applied):
            readback = "unavailable"
        elif _matches(applied, target):
            readback = "confirmed"
        else:
            readback = "mismatch"
        detail = _gpd_detail(
            variant="power-only",
            primary_exit=primary_exit,
            exit_code=fallback_exit,
            readback=readback,
        )
        if fallback_exit:
            return TdpResult(watts, applied, False, detail)
        if _unreadable(applied):
            return TdpResult(watts, None, True, detail)
        return TdpResult(watts, applied, _matches(applied, target), detail)

    def _apply(self, target: int, *, include_temp: bool = True) -> int:
        mw = str(target * 1000)
        argv = [
            self._bin,
            "--stapm-limit", mw,
            "--fast-limit", mw,
            "--slow-limit", mw,
        ]
        if include_temp:
            argv.extend(["--tctl-temp", "90"])
        res = self._runner(argv, capture_output=True, text=True, timeout=5, env=_clean_env())
        return int(getattr(res, "returncode", 0) or 0)

    def read_applied(self) -> int | None:
        return self._read_applied()

    def _read_applied(self, *, require_zero_exit: bool = False) -> int | None:
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
        if require_zero_exit and getattr(res, "returncode", 0):
            return None
        out = getattr(res, "stdout", "") or ""
        return _parse_stapm(out)
