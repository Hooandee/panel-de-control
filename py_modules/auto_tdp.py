from collections import deque
from dataclasses import dataclass
import math
import time

BOOST_DEADBAND_W = 1
_LEGACY_UP_GPU = 97
_LEGACY_DOWN_GPU = 88
_LEGACY_RECENT = 2
_LEGACY_SLACK_HOLD = 6
_LEGACY_DOWN_GAIN = 1 / 3.0


def is_boosting(watts, pl1):
    if watts is None:
        return None
    return round(watts) > round(pl1) + BOOST_DEADBAND_W


def decide(
    current_pl1,
    gpu_window,
    slack_ticks,
    min_w,
    max_w,
    *,
    up_step=2,
    down_step=1,
    max_down_step=5,
):
    """Compatibility contract for the existing Windows/shared-fixture brain.

    The SteamOS runtime uses :class:`AutoTdpController`; this pure function remains
    available until the independently shipped Windows implementation is redesigned.
    """
    current = max(min_w, min(int(current_pl1), max_w))
    gpu = [sample for sample in gpu_window if sample is not None]
    if not gpu:
        return current, slack_ticks
    if max(gpu[-_LEGACY_RECENT:]) >= _LEGACY_UP_GPU:
        return max(min_w, min(current + up_step, max_w)), 0
    average = sum(gpu) / len(gpu)
    if average > _LEGACY_DOWN_GPU:
        return current, 0
    slack = slack_ticks + 1
    if slack < _LEGACY_SLACK_HOLD:
        return current, slack
    gap = _LEGACY_DOWN_GPU - average
    step_size = round(gap * _LEGACY_DOWN_GAIN)
    step_size = max(down_step, min(step_size, max_down_step))
    return max(min_w, current - step_size), 0


@dataclass(frozen=True)
class AutoTdpDecision:
    setpoint: int
    state: str
    reason: str
    changed: bool
    fps: float | None
    target_fps: int

    def as_dict(self):
        return {
            "setpoint": self.setpoint,
            "state": self.state,
            "reason": self.reason,
            "changed": self.changed,
            "fps": self.fps,
            "target_fps": self.target_fps,
        }


class AutoTdpController:
    def __init__(
        self,
        initial_w,
        min_w,
        max_w,
        target_fps,
        *,
        clock=time.monotonic,
        warmup_s=4.0,
        stable_s=8.0,
        settle_s=6.0,
        cooldown_s=12.0,
        qualification_s=8.0,
        qualification_gpu=35.0,
        low_load_qualification_s=12.0,
        load_shift_ratio=0.55,
        failed_probe_retry_s=120.0,
        stale_recovery_s=11.0,
        stale_recovery_gpu=90.0,
        recovery_interval_s=2.0,
        stale_progress_s=11.0,
    ):
        self.min_w = int(min_w)
        self.max_w = max(self.min_w, int(max_w))
        self.target_fps = max(1, int(target_fps))
        self.setpoint = self._clamp(initial_w)
        self._starting_w = self.setpoint
        self._clock = clock
        self._warmup_s = max(0.0, float(warmup_s))
        self._stable_s = max(0.0, float(stable_s))
        self._settle_s = max(0.0, float(settle_s))
        self._cooldown_s = max(0.0, float(cooldown_s))
        self._qualification_s = max(0.0, float(qualification_s))
        self._qualification_gpu = max(0.0, float(qualification_gpu))
        self._low_load_qualification_s = max(
            self._qualification_s,
            float(low_load_qualification_s),
        )
        self._load_shift_ratio = max(0.0, min(float(load_shift_ratio), 1.0))
        self._failed_probe_retry_s = max(0.0, float(failed_probe_retry_s))
        self._stale_recovery_s = max(0.0, float(stale_recovery_s))
        self._stale_recovery_gpu = max(0.0, float(stale_recovery_gpu))
        self._recovery_interval_s = max(0.0, float(recovery_interval_s))
        self._stale_progress_s = max(0.0, float(stale_progress_s))
        self._active_since = None
        self._stable_since = None
        self._qualification_since = None
        self._qualification_samples = deque(maxlen=32)
        self._low_load_since = None
        self._low_load_samples = deque(maxlen=64)
        self._gameplay_qualified = False
        self._low_load_qualified = False
        self._gameplay_gpu_baseline = None
        self._settle_since = None
        self._settle_samples = 0
        self._cooldown_until = 0.0
        self._probe_retry_at = 0.0
        self._probe_from = None
        self._probe_baseline_fps = None
        self._pending_apply_from = None
        self._last_low_fps_at = None
        self._last_recovery_at = None
        self._last_fresh_at = None
        self._stale_pending = False
        self._fps_window = deque(maxlen=32)
        self.state = "warming"
        self.reason = "starting"
        self.fps = None

    def _clamp(self, watts):
        return max(self.min_w, min(int(watts), self.max_w))

    def _result(self, state, reason, previous):
        self.state = state
        self.reason = reason
        return AutoTdpDecision(
            setpoint=self.setpoint,
            state=state,
            reason=reason,
            changed=self.setpoint != previous,
            fps=self.fps,
            target_fps=self.target_fps,
        )

    def _reset_qualification_candidates(self):
        self._qualification_since = None
        self._qualification_samples.clear()
        self._low_load_since = None
        self._low_load_samples.clear()

    def _reset_stability(self):
        self._fps_window.clear()
        self._stable_since = None

    def _reset_probe_settlement(self):
        self._settle_since = None
        self._settle_samples = 0

    def _clear_probe(self):
        self._probe_from = None
        self._probe_baseline_fps = None

    def _clear_recovery_evidence(self):
        self._last_low_fps_at = None
        self._last_recovery_at = None

    def _pause(self, reason, previous):
        self._reset_stability()
        if self._probe_from is not None:
            self.setpoint = self._clamp(self._probe_from)
            self._probe_retry_at = max(
                self._probe_retry_at,
                self._clock() + self._failed_probe_retry_s,
            )
        self._clear_probe()
        self._pending_apply_from = None
        self._active_since = None
        self._reset_qualification_candidates()
        self._gameplay_qualified = False
        self._low_load_qualified = False
        self._gameplay_gpu_baseline = None
        self._reset_probe_settlement()
        self._cooldown_until = 0.0
        self._clear_recovery_evidence()
        self._last_fresh_at = None
        self._stale_pending = False
        return self._result("paused", reason, previous)

    def _hold(self, reason, previous):
        self._reset_stability()
        self._reset_qualification_candidates()
        self._reset_probe_settlement()
        if self._probe_from is not None:
            self._cooldown_until = 0.0
        if self._pending_apply_from is not None:
            self.setpoint = self._clamp(self._pending_apply_from)
            self._pending_apply_from = None
            if self._probe_from == self.setpoint:
                self._clear_probe()
        self._clear_recovery_evidence()
        return self._result("paused", reason, previous)

    def _recover(self, previous, now, reason="fps_below_target"):
        self._reset_stability()
        self._reset_qualification_candidates()
        self._reset_probe_settlement()
        self._cooldown_until = now + self._cooldown_s
        self._last_recovery_at = now
        if self._probe_from is not None:
            self.setpoint = self._clamp(self._probe_from)
            self._clear_probe()
            self._probe_retry_at = now + self._failed_probe_retry_s
            self._pending_apply_from = None
            return self._result("recovering", "probe_regressed", previous)
        self.setpoint = self._clamp(self.setpoint + 2)
        if self.setpoint == previous:
            return self._result("recovering", "at_maximum", previous)
        self._pending_apply_from = previous
        return self._result("recovering", reason, previous)

    def _has_recent_low_fps_evidence(self, signal_reason, gpu_busy, now):
        return bool(
            signal_reason == "fps_stale"
            and self._last_low_fps_at is not None
            and now - self._last_low_fps_at <= self._stale_recovery_s
            and gpu_busy is not None
            and gpu_busy >= self._stale_recovery_gpu
        )

    def _recovery_step_due(self, now):
        return bool(
            self._last_recovery_at is None
            or now - self._last_recovery_at >= self._recovery_interval_s
        )

    def _gpu_value(self, gpu_busy):
        if gpu_busy is None:
            return None
        try:
            value = float(gpu_busy)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(value) or value < 0:
            return None
        return value

    def _qualify_gameplay(self, gpu_busy, now):
        if self._gameplay_qualified:
            return True
        if gpu_busy is None:
            self._reset_qualification_candidates()
            return False
        if gpu_busy >= self._qualification_gpu:
            self._low_load_since = None
            self._low_load_samples.clear()
            if self._qualification_since is None:
                self._qualification_since = now
            self._qualification_samples.append(gpu_busy)
            if now - self._qualification_since < self._qualification_s:
                return False
            baseline = self._qualification_samples
            self._low_load_qualified = False
        else:
            self._qualification_since = None
            self._qualification_samples.clear()
            if self.fps < self.target_fps - 0.5:
                self._low_load_since = None
                self._low_load_samples.clear()
                return False
            if self._low_load_since is None:
                self._low_load_since = now
            self._low_load_samples.append(gpu_busy)
            if now - self._low_load_since < self._low_load_qualification_s:
                return False
            baseline = self._low_load_samples
            self._low_load_qualified = True
        self._gameplay_qualified = True
        self._gameplay_gpu_baseline = sum(baseline) / len(baseline)
        self._reset_qualification_candidates()
        return True

    def _load_shifted(self, gpu_busy):
        return bool(
            self._gameplay_qualified
            and gpu_busy is not None
            and self._gameplay_gpu_baseline is not None
            and gpu_busy < self._gameplay_gpu_baseline * self._load_shift_ratio
        )

    def _load_increased(self, gpu_busy):
        return bool(
            self._gameplay_qualified
            and self._low_load_qualified
            and gpu_busy is not None
            and self._gameplay_gpu_baseline is not None
            and gpu_busy >= max(
                self._qualification_gpu,
                self._gameplay_gpu_baseline / max(self._load_shift_ratio, 0.1),
            )
        )

    def _restore_starting_tdp(self, previous, now):
        self._reset_stability()
        self._reset_probe_settlement()
        self._cooldown_until = now + self._cooldown_s
        self._clear_probe()
        self._gameplay_qualified = False
        self._low_load_qualified = False
        self._gameplay_gpu_baseline = None
        self.setpoint = self._clamp(max(self.setpoint, self._starting_w))
        self._pending_apply_from = previous if self.setpoint != previous else None
        return self._result("recovering", "load_increase", previous)

    def _update_gameplay_baseline(self, gpu_busy):
        if gpu_busy is None or self._gameplay_gpu_baseline is None:
            return
        self._gameplay_gpu_baseline = (
            self._gameplay_gpu_baseline * 0.9 + gpu_busy * 0.1
        )

    def step(self, *, fps, signal_reason, gpu_busy=None):
        previous = self.setpoint
        now = self._clock()
        gpu = self._gpu_value(gpu_busy)
        try:
            self.fps = float(fps) if fps is not None else None
        except (TypeError, ValueError, OverflowError):
            self.fps = None
        if (
            signal_reason != "ok"
            or self.fps is None
            or not math.isfinite(self.fps)
            or self.fps <= 0
        ):
            if signal_reason == "fps_stale":
                self._stale_pending = True
            if self._has_recent_low_fps_evidence(signal_reason, gpu, now):
                if self._recovery_step_due(now):
                    return self._recover(previous, now, "fps_stale_recovery")
                return self._result(
                    "recovering",
                    "fps_stale_recovery_wait",
                    previous,
                )
            reason = signal_reason if signal_reason != "ok" else "fps_unavailable"
            if reason == "fps_stale" and self._probe_from is None:
                return self._result("paused", reason, previous)
            return self._pause(reason, previous)

        bridged_stale = self._stale_pending
        if (
            bridged_stale
            and self._last_fresh_at is not None
            and now - self._last_fresh_at > self._stale_progress_s
        ):
            self._reset_stability()
            self._reset_qualification_candidates()
            self._gameplay_qualified = False
            self._low_load_qualified = False
            self._gameplay_gpu_baseline = None
            self._active_since = None
        self._stale_pending = False
        self._last_fresh_at = now

        if self._load_increased(gpu):
            self._clear_recovery_evidence()
            return self._restore_starting_tdp(previous, now)

        if self.fps < self.target_fps - 2.0:
            self._last_low_fps_at = now
            return self._recover(previous, now)

        self._clear_recovery_evidence()

        if self._load_shifted(gpu):
            return self._hold("load_shift", previous)

        if not self._qualify_gameplay(gpu, now):
            self._reset_stability()
            return self._result("holding", "awaiting_gameplay", previous)
        self._update_gameplay_baseline(gpu)

        if self._probe_from is not None:
            regressed = (
                self.fps < self.target_fps - 0.5
                or (
                    self._probe_baseline_fps is not None
                    and self.fps < self._probe_baseline_fps - 1.0
                )
            )
            if regressed:
                return self._recover(previous, now)
            if self._settle_since is None:
                self._settle_since = now
                self._settle_samples = 0
            self._settle_samples += 1
            if (
                now - self._settle_since < self._settle_s
                or self._settle_samples < 2
            ):
                return self._result("optimizing", "settling_probe", previous)
            if self._cooldown_until <= 0.0:
                self._cooldown_until = now + self._cooldown_s
            if now < self._cooldown_until:
                return self._result("holding", "cooldown", previous)
            self._clear_probe()
            self._reset_probe_settlement()
            self._cooldown_until = 0.0
            self._reset_stability()
            return self._result("holding", "probe_stable", previous)

        if self._active_since is None:
            self._active_since = now
        if now - self._active_since < self._warmup_s:
            return self._result("warming", "warming", previous)

        if now < self._probe_retry_at:
            return self._result("holding", "cooldown", previous)

        if now < self._cooldown_until:
            return self._result("holding", "cooldown", previous)

        self._fps_window.append((now, min(self.fps, float(self.target_fps))))
        window_s = (
            max(self._stable_s, self._stale_progress_s)
            if bridged_stale
            else self._stable_s
        )
        while self._fps_window and now - self._fps_window[0][0] > window_s:
            self._fps_window.popleft()
        values = [sample for _at, sample in self._fps_window]
        sample_stable = (
            self.fps >= self.target_fps - 0.5
            and (not values or max(values) - min(values) <= 2.0)
        )
        if not sample_stable:
            self._reset_stability()
            return self._result("holding", "building_stability", previous)
        if self._stable_since is None:
            self._stable_since = now
        stable = (
            now - self._stable_since >= self._stable_s
            and len(self._fps_window) >= 2
            and min(values) >= self.target_fps - 0.5
            and max(values) - min(values) <= 2.0
        )
        if not stable:
            return self._result("holding", "building_stability", previous)

        self._reset_stability()
        if self.setpoint <= self.min_w:
            return self._result("holding", "at_minimum", previous)
        self._probe_from = self.setpoint
        self._probe_baseline_fps = sum(values) / len(values)
        self.setpoint = self._clamp(self.setpoint - 1)
        self._settle_since = now
        self._settle_samples = 0
        self._cooldown_until = 0.0
        self._probe_retry_at = 0.0
        self._pending_apply_from = previous
        return self._result("optimizing", "probe_down", previous)

    def confirm_apply(self):
        self._pending_apply_from = None

    def reject_apply(self, reason="apply_unconfirmed"):
        previous = self.setpoint
        if self._pending_apply_from is not None:
            self.setpoint = self._clamp(self._pending_apply_from)
        return self._pause(reason, previous)

    def pause(self, reason):
        return self._pause(reason, self.setpoint)

    def hold(self, reason):
        return self._hold(reason, self.setpoint)

    def snapshot(self):
        return AutoTdpDecision(
            setpoint=self.setpoint,
            state=self.state,
            reason=self.reason,
            changed=False,
            fps=self.fps,
            target_fps=self.target_fps,
        )
