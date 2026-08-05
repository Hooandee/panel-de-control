import asyncio
import glob
import os
import time


def read_on_ac(root="/"):
    """True if any power supply of type 'Mains' is online. Never raises."""
    for d in glob.glob(os.path.join(root, "sys/class/power_supply", "*")):
        try:
            with open(os.path.join(d, "type")) as f:
                if f.read().strip() != "Mains":
                    continue
            with open(os.path.join(d, "online")) as f:
                if f.read().strip() == "1":
                    return True
        except OSError:
            continue
    return False


def _read_wakeup_count(root="/"):
    try:
        with open(os.path.join(root, "sys/power/wakeup_count")) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def _read_suspend_time():
    try:
        return (
            time.clock_gettime(time.CLOCK_BOOTTIME)
            - time.clock_gettime(time.CLOCK_MONOTONIC)
        )
    except (AttributeError, OSError):
        return None


class LifecycleManager:
    """Re-applies controls after confirmed resume and AC/DC transitions.
    Decision logic is in check(now); run() is a thin async loop around it."""

    # Re-apply again this many seconds after an AC change: the firmware briefly reverts
    # to its default (an Ally drops to ~12 W on unplug) and a single re-apply mid-
    # transition can be lost, so re-assert once it has settled.
    _AC_SETTLE_RETRIES = (2.0, 4.0)
    # Resume has the same problem: the firmware reverts ppt to its default on wake and can
    # do so after the base delay, so a lone re-apply is lost. Re-assert across a window.
    _RESUME_SETTLE_RETRIES = (2.0, 5.0, 9.0)
    _MIN_SUSPEND_S = 0.5
    _SUSPEND_EVIDENCE_MAX_AGE_S = 10.0

    def __init__(self, apply_cb, root="/", wakeup_delay=4.0, interval=2.0,
                 read_wakeup=None, read_ac=None, reassert_cb=None,
                 read_suspend=None, event_cb=None, resume_apply_cb=None):
        self._apply = apply_cb
        self._resume_apply = resume_apply_cb or apply_cb
        # Settle-retries re-assert only the power rails, not the full re-apply; fall back to
        # the full apply when not given.
        self._reassert = reassert_cb or apply_cb
        self._root = root
        self._wakeup_delay = wakeup_delay
        self._interval = interval
        self._read_wakeup = read_wakeup or (lambda: _read_wakeup_count(root))
        self._read_ac = read_ac or (lambda: read_on_ac(root))
        self._read_suspend = read_suspend or _read_suspend_time
        self._event_cb = event_cb
        self._last_wakeup = None
        self._last_suspend = None
        self._suspend_evidence_since = None
        self._suspend_clock_available = False
        self._last_ac = None
        self._resume_count = 0
        self._ignored_wakeup_changes = 0
        self._ac_transition_count = 0
        self._apply_failures = 0
        self._last_apply_failure = None
        self._poll_failures = 0
        self._last_poll_failure = None
        self._last_event = None
        self._pending = []        # times for the full re-apply (base resume delay)
        self._pending_light = []  # times for the TDP-only settle-retries
        self._task = None

    def _emit(self, event, **details):
        record = {"event": event, **details}
        self._last_event = record
        if self._event_cb is None:
            return
        try:
            self._event_cb(dict(record))
        except Exception:  # noqa: BLE001 - diagnostics must not break lifecycle
            pass

    @staticmethod
    def _is_logarithmic_sample(count):
        return count > 0 and count & (count - 1) == 0

    def diagnostics(self):
        return {
            "suspend_clock_available": self._suspend_clock_available,
            "resume_count": self._resume_count,
            "ignored_wakeup_changes": self._ignored_wakeup_changes,
            "ac_transition_count": self._ac_transition_count,
            "apply_failures": self._apply_failures,
            "last_apply_failure": (
                dict(self._last_apply_failure)
                if self._last_apply_failure is not None
                else None
            ),
            "poll_failures": self._poll_failures,
            "last_poll_failure": (
                dict(self._last_poll_failure)
                if self._last_poll_failure is not None
                else None
            ),
            "pending_full_reapplies": len(self._pending),
            "pending_tdp_reasserts": len(self._pending_light),
            "last_event": (
                dict(self._last_event)
                if self._last_event is not None
                else None
            ),
        }

    def _safe(self, cb, ac, operation):
        try:
            cb(ac)
        except Exception as exc:  # noqa: BLE001 - one bad apply must not abort check()
            self._apply_failures += 1
            failure = {
                "operation": operation,
                "on_ac": bool(ac),
                "error": type(exc).__name__,
                "failure_count": self._apply_failures,
            }
            self._last_apply_failure = failure
            self._emit("apply_failed", **failure)

    def _record_poll_failure(self, stage, exc):
        self._poll_failures += 1
        failure = {
            "stage": stage,
            "error": type(exc).__name__,
            "failure_count": self._poll_failures,
        }
        self._last_poll_failure = failure
        if self._is_logarithmic_sample(self._poll_failures):
            self._emit("poll_failed", **failure)

    def _read_input(self, stage, reader):
        try:
            return True, reader()
        except Exception as exc:  # noqa: BLE001 - one bad reader must not kill the poller
            self._record_poll_failure(stage, exc)
            return False, None

    def _fire_due(self, pending, cb, now, operation, ac):
        """Fire cb once (with live AC) if any scheduled time is due; return the times left."""
        if not any(now >= t for t in pending):
            return pending
        self._safe(cb, ac, operation)
        return [t for t in pending if now < t]

    def check(self, now):
        wakeup_ok, wc = self._read_input("read_wakeup", self._read_wakeup)
        ac_ok, ac = self._read_input("read_ac", self._read_ac)
        suspend_ok, suspend_time = self._read_input(
            "read_suspend", self._read_suspend
        )
        if not wakeup_ok or not ac_ok:
            return
        if not suspend_ok:
            suspend_time = None
        self._suspend_clock_available = suspend_time is not None
        # initialize on first observation (no event)
        if self._last_wakeup is None:
            self._last_wakeup, self._last_ac = wc, ac
            self._last_suspend = suspend_time
            self._emit(
                "baseline",
                on_ac=bool(ac),
                suspend_clock_available=suspend_time is not None,
            )
            return
        # resume → full re-apply after the base delay, then TDP-only settle retries
        suspend_delta = (
            suspend_time - self._last_suspend
            if suspend_time is not None and self._last_suspend is not None
            else 0.0
        )
        wakeup_changed = wc != self._last_wakeup
        suspend_evidence = suspend_delta >= self._MIN_SUSPEND_S
        stale_suspend_evidence = (
            suspend_evidence
            and self._suspend_evidence_since is not None
            and (
                now - self._suspend_evidence_since
                > self._SUSPEND_EVIDENCE_MAX_AGE_S
            )
        )
        if stale_suspend_evidence:
            self._last_suspend = suspend_time
            self._suspend_evidence_since = None
            suspend_evidence = False
        elif suspend_evidence and not wakeup_changed:
            if self._suspend_evidence_since is None:
                self._suspend_evidence_since = now
        if wakeup_changed and suspend_evidence:
            self._resume_count += 1
            base = now + self._wakeup_delay
            self._pending.append(base)
            self._pending_light.extend(base + d for d in self._RESUME_SETTLE_RETRIES)
            self._emit(
                "resume_detected",
                suspend_seconds=round(suspend_delta, 3),
                full_delay_seconds=self._wakeup_delay,
                tdp_settle_retries=len(self._RESUME_SETTLE_RETRIES),
            )
        elif wakeup_changed:
            self._ignored_wakeup_changes += 1
            if self._is_logarithmic_sample(self._ignored_wakeup_changes):
                reason = (
                    "stale_suspend_evidence"
                    if stale_suspend_evidence
                    else "suspend_clock_unavailable"
                    if suspend_time is None or self._last_suspend is None
                    else "suspend_delta_below_threshold"
                )
                self._emit(
                    "wakeup_change_ignored",
                    reason=reason,
                    ignored_count=self._ignored_wakeup_changes,
                )
        self._last_wakeup = wc
        if wakeup_changed:
            self._last_suspend = suspend_time
            self._suspend_evidence_since = None
        # AC transition → full re-apply now, then TDP-only re-asserts as the firmware settles
        if ac != self._last_ac:
            self._last_ac = ac
            self._ac_transition_count += 1
            self._safe(self._apply, ac, "ac-full-reapply")
            self._pending_light.extend(now + d for d in self._AC_SETTLE_RETRIES)
            self._emit(
                "ac_changed",
                on_ac=bool(ac),
                tdp_settle_retries=len(self._AC_SETTLE_RETRIES),
            )
        # fire scheduled re-applies whose delay has elapsed (re-reading AC live)
        self._pending = self._fire_due(
            self._pending, self._resume_apply, now,
            "resume-full-reapply", ac
        )
        self._pending_light = self._fire_due(
            self._pending_light, self._reassert, now, "tdp-settle-reassert", ac
        )

    async def run(self):
        while True:
            try:
                self.check(time.time())
            except Exception as exc:  # noqa: BLE001 - the poller must never die
                self._record_poll_failure("check", exc)
            await asyncio.sleep(self._interval)

    def start(self):
        if self._task is None:
            self._task = asyncio.ensure_future(self.run())

    def stop(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None
