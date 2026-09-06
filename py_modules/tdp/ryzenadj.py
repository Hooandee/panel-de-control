import os
import re
import shutil
import subprocess

from tdp.backend import TDPBackend
from tdp.types import TdpLimits, TdpResult

# The sustained (STAPM) limit line of `ryzenadj -i`.
_STAPM_RE = re.compile(r"STAPM LIMIT\s*\|\s*([\d.]+)", re.IGNORECASE)
_FAST_RE = re.compile(r"PPT LIMIT FAST\s*\|\s*([\d.]+)", re.IGNORECASE)
_SLOW_RE = re.compile(r"PPT LIMIT SLOW\s*\|\s*([\d.]+)", re.IGNORECASE)

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


def _parse_snapshot(out: str) -> dict[str, int] | None:
    values = {}
    for key, pattern in (("stapm", _STAPM_RE), ("fast", _FAST_RE), ("slow", _SLOW_RE)):
        match = pattern.search(out)
        if not match:
            return None
        try:
            value = round(float(match.group(1)))
        except ValueError:
            return None
        if value <= 0:
            return None
        values[key] = value
    return values


def _snapshot_matches(snapshot, target):
    return bool(snapshot) and all(_matches(value, target) for value in snapshot.values())


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
                 write_max: int | None = None, power_only_retry: bool = False,
                 require_readback: bool = False):
        self._fallback = fallback
        # Writes clamp to the absolute ceiling (cooler_max); get_limits keeps the base.
        self._write_limits = fallback.with_cooler(write_max)
        self._runner = runner
        self._bin = resolve()
        self._power_only_retry = power_only_retry
        self._require_readback = bool(require_readback)
        self.supported = self._bin is not None
        self._readback_state = (
            "pending"
            if self.supported and self._require_readback
            else "not_required" if self.supported else "binary_missing"
        )
        self._last_readback_failure = None

    def get_limits(self) -> TdpLimits:
        return self._fallback

    def _required_snapshot(self):
        if not self.supported or self._readback_state.startswith("circuit_open"):
            return None
        snapshot = self._read_snapshot(require_zero_exit=True)
        if snapshot is None:
            self._readback_state = "circuit_open_initial"
            self._last_readback_failure = (
                "ryzenadj required readback unavailable before write; circuit open"
            )
            self.supported = False
            return None
        self._readback_state = "ready"
        return snapshot

    def probe(self) -> bool:
        if not self._require_readback:
            return bool(self.supported)
        return self._required_snapshot() is not None

    @property
    def probe_pending(self) -> bool:
        return self._readback_state == "pending"

    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        if not self.supported:
            detail = self._last_readback_failure or "ryzenadj binary not found"
            return TdpResult(watts, None, False, detail)
        baseline = self._required_snapshot() if self._require_readback else None
        if self._require_readback and baseline is None:
            return TdpResult(watts, None, False, self._last_readback_failure)
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
                primary_exit = self._apply(
                    target,
                    include_temp=not self._require_readback,
                )
            except (OSError, subprocess.SubprocessError) as e:
                if self._require_readback:
                    return self._handle_strict_failure(
                        watts,
                        baseline,
                        f"ryzenadj apply failed ({type(e).__name__})",
                        open_circuit=True,
                    )
                if self._power_only_retry:
                    return TdpResult(
                        watts, None, False,
                        f"ryzenadj primary failed ({type(e).__name__})",
                    )
                return TdpResult(watts, None, False, f"ryzenadj failed: {e}")
            if self._power_only_retry and primary_exit:
                return self._recover_gpd(watts, target, primary_exit, baseline)
            strict_snapshot = (
                self._read_snapshot(require_zero_exit=True)
                if self._require_readback
                else None
            )
            if self._require_readback and strict_snapshot is None:
                return self._handle_strict_failure(
                    watts,
                    baseline,
                    "ryzenadj required readback lost",
                    open_circuit=True,
                )
            applied = (
                strict_snapshot["stapm"]
                if strict_snapshot is not None
                else self._read_applied()
            )
            if strict_snapshot is not None and _snapshot_matches(strict_snapshot, target):
                return TdpResult(watts, applied, True, "")
            if _unreadable(applied):
                continue  # re-assert once, then treat as unconfirmed
            if strict_snapshot is None and _matches(applied, target):
                return TdpResult(watts, applied, True, "")
        if _unreadable(applied):
            if self._require_readback:
                return TdpResult(
                    watts,
                    None,
                    False,
                    "ryzenadj required readback unavailable",
                )
            return TdpResult(watts, None, True, "applied (limit readback unavailable)")
        if self._require_readback and strict_snapshot is not None:
            held = ", ".join(
                f"{rail}={value}" for rail, value in strict_snapshot.items()
            )
            mismatch = f"ryzenadj limits did not stick (wanted {target}, holds {held})"
        else:
            mismatch = f"ryzenadj limit did not stick (wanted {target}, holds {applied})"
        if self._require_readback:
            return self._handle_strict_failure(
                watts,
                baseline,
                mismatch,
                open_circuit=False,
            )
        return TdpResult(watts, applied, False, mismatch)

    def _recover_gpd(
        self,
        watts: int,
        target: int,
        primary_exit: int,
        baseline: dict[str, int] | None = None,
    ) -> TdpResult:
        strict_snapshot = (
            self._read_snapshot(require_zero_exit=True)
            if self._require_readback
            else None
        )
        if self._require_readback and strict_snapshot is None:
            return self._handle_strict_failure(
                watts,
                baseline,
                "ryzenadj required readback lost",
                open_circuit=True,
            )
        applied = (
            strict_snapshot["stapm"]
            if strict_snapshot is not None
            else self._read_applied(require_zero_exit=True)
        )
        if strict_snapshot is not None and _snapshot_matches(strict_snapshot, target):
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
        if strict_snapshot is None and _matches(applied, target):
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
            if self._require_readback:
                return self._handle_strict_failure(
                    watts,
                    baseline,
                    f"ryzenadj power-only failed ({type(e).__name__}) "
                    f"primary_exit={int(primary_exit)}",
                    open_circuit=True,
                )
            return TdpResult(
                watts,
                applied,
                False,
                f"ryzenadj power-only failed ({type(e).__name__}) "
                f"primary_exit={int(primary_exit)}",
            )
        strict_snapshot = (
            self._read_snapshot(require_zero_exit=True)
            if self._require_readback
            else None
        )
        if self._require_readback and strict_snapshot is None:
            return self._handle_strict_failure(
                watts,
                baseline,
                "ryzenadj required readback lost",
                open_circuit=True,
            )
        applied = (
            strict_snapshot["stapm"]
            if strict_snapshot is not None
            else self._read_applied(require_zero_exit=True)
        )
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
            if self._require_readback:
                return self._handle_strict_failure(
                    watts,
                    baseline,
                    detail,
                    open_circuit=True,
                )
            return TdpResult(watts, applied, False, detail)
        if _unreadable(applied):
            return TdpResult(watts, None, not self._require_readback, detail)
        confirmed = (
            _snapshot_matches(strict_snapshot, target)
            if strict_snapshot is not None
            else _matches(applied, target)
        )
        if self._require_readback and not confirmed:
            return self._handle_strict_failure(
                watts,
                baseline,
                detail,
                open_circuit=False,
            )
        return TdpResult(watts, applied, confirmed, detail)

    def _handle_strict_failure(
        self,
        watts: int,
        baseline: dict[str, int] | None,
        detail: str,
        *,
        open_circuit: bool,
    ) -> TdpResult:
        restore = self._restore_snapshot(baseline)
        if open_circuit or restore != "confirmed":
            self._readback_state = (
                "circuit_open_restored"
                if restore == "confirmed"
                else "circuit_open_unresolved"
            )
            self.supported = False
            suffix = "; circuit open"
        else:
            self._readback_state = "ready"
            suffix = ""
        self._last_readback_failure = f"{detail}; baseline restore {restore}{suffix}"
        return TdpResult(watts, None, False, self._last_readback_failure)

    def _restore_snapshot(self, baseline) -> str:
        if not isinstance(baseline, dict):
            return "unresolved"
        try:
            exit_code = self._apply_limits(
                baseline["stapm"],
                baseline["fast"],
                baseline["slow"],
                include_temp=False,
            )
        except (KeyError, OSError, subprocess.SubprocessError):
            return "unresolved"
        if exit_code:
            return "unresolved"
        restored = self._read_snapshot(require_zero_exit=True)
        return "confirmed" if restored == baseline else "unresolved"

    def _apply(self, target: int, *, include_temp: bool = True) -> int:
        return self._apply_limits(
            target,
            target,
            target,
            include_temp=include_temp,
        )

    def _apply_limits(self, stapm: int, fast: int, slow: int, *, include_temp: bool) -> int:
        argv = [
            self._bin,
            "--stapm-limit", str(stapm * 1000),
            "--fast-limit", str(fast * 1000),
            "--slow-limit", str(slow * 1000),
        ]
        if include_temp:
            argv.extend(["--tctl-temp", "90"])
        res = self._runner(argv, capture_output=True, text=True, timeout=5, env=_clean_env())
        return int(getattr(res, "returncode", 0) or 0)

    def read_applied(self) -> int | None:
        return self._read_applied()

    def diagnostics(self) -> dict:
        return {
            "readback_required": self._require_readback,
            "readback_state": self._readback_state,
            "last_readback_failure": self._last_readback_failure,
        }

    def _read_applied(self, *, require_zero_exit: bool = False) -> int | None:
        if not self.supported:
            return None
        out = self._read_info(require_zero_exit=require_zero_exit)
        return _parse_stapm(out) if out is not None else None

    def _read_snapshot(self, *, require_zero_exit: bool = False):
        if not self.supported:
            return None
        out = self._read_info(require_zero_exit=require_zero_exit)
        return _parse_snapshot(out) if out is not None else None

    def _read_info(self, *, require_zero_exit: bool = False) -> str | None:
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
        return getattr(res, "stdout", "") or ""
