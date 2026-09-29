import glob
import os
from dataclasses import dataclass

# ASUS firmware (ROG Ally X RC72LA) loads the limits of the new platform
# profile into the SMU while firmware-attributes keeps echoing the last value
# written, so the rails read in sync while the chip draws far above them. A
# fresh write of the same rails restores them; the measured package power is
# the fallback signal when the profile change itself goes unseen.
SUSTAIN_S = 20.0
SEVERE_RATIO = 1.5
SEVERE_SUSTAIN_S = 6.0
VERIFY_S = 10.0
MIN_TARGET_W = 10
MARGIN_W = 3.0
MARGIN_RATIO = 0.10
UNRESOLVED_COOLDOWN_S = (60.0, 180.0, 600.0)
MAX_UNRESOLVED = 3
RESTORE_READINGS = 2
MAX_RESTORED_PER_SESSION = 30

PROFILE_SETTLE_S = (1.0, 4.0, 10.0)

REWRITE = "rewrite"
NUDGE = "nudge"


def read_platform_profiles(root="/"):
    paths = sorted(
        glob.glob(os.path.join(root, "sys/class/platform-profile/*/profile"))
    ) + [os.path.join(root, "sys/firmware/acpi/platform_profile")]
    for supply in sorted(glob.glob(os.path.join(root, "sys/class/power_supply/*"))):
        try:
            with open(os.path.join(supply, "type")) as handle:
                if handle.read().strip() == "Mains":
                    paths.append(os.path.join(supply, "online"))
        except OSError:
            continue
    profiles = []
    for path in paths:
        try:
            with open(path) as handle:
                profiles.append((path, handle.read().strip()))
        except OSError:
            continue
    return tuple(profiles) or None


class PlatformProfileWatch:
    def __init__(self, read=read_platform_profiles):
        self._read = read
        self._profiles = None
        self._changed_at = None
        self._steps_done = 0
        self.last_change = None

    def observe(self, now):
        profiles = self._read()
        if profiles is None:
            return False
        if self._profiles is not None and profiles != self._profiles:
            self._changed_at = now
            self._steps_done = 0
            self.last_change = {
                "at": round(now, 3),
                "from": [value for _, value in self._profiles],
                "to": [value for _, value in profiles],
            }
        self._profiles = profiles
        if self._changed_at is None or self._steps_done >= len(PROFILE_SETTLE_S):
            return False
        if now - self._changed_at < PROFILE_SETTLE_S[self._steps_done]:
            return False
        self._steps_done += 1
        return True


def sustained_ceiling(target):
    pl1 = target.get("pl1")
    if pl1 is None:
        return None
    return max(int(pl1), int(target.get("pl2", pl1)))


def overshoot_limit(ceiling):
    return ceiling + max(MARGIN_W, ceiling * MARGIN_RATIO)


def nudged_target(target, bounds):
    """One watt off on every rail that can move, so the driver sees a change."""
    nudged, moved = {}, False
    for rail, value in target.items():
        lo, hi = bounds.get(rail, (value, value))
        if value - 1 >= lo:
            nudged[rail] = value - 1
            moved = True
        elif value + 1 <= hi:
            nudged[rail] = value + 1
            moved = True
        else:
            nudged[rail] = value
    return nudged if moved else None


@dataclass
class _Episode:
    method: str
    target: dict
    verify_until: float
    peak_w: float
    under_readings: int = 0


class HiddenOvershootMonitor:
    def __init__(self):
        self._context = None
        self.observed_at = None
        self._reset_session()

    def _reset_session(self):
        self._over_since = None
        self._over_target = None
        self._over_peak = 0.0
        self._severe_since = None
        self._episode = None
        self._preferred = REWRITE
        self._unresolved = 0
        self._restored_total = 0
        self._cooldown_until = 0.0
        self._last = None

    def _enter(self, context):
        if context != self._context:
            self._context = context
            self._reset_session()

    def observe(self, now, context, watts, target, eligible):
        self._enter(context)
        ceiling = sustained_ceiling(target or {})
        if (
            not eligible
            or watts is None
            or ceiling is None
            or int(target["pl1"]) < MIN_TARGET_W
        ):
            self._over_since = None
            self._drop_episode()
            self._forget_unresolved()
            return None
        self.observed_at = now
        if self._last is not None and self._last["ceiling_w"] != ceiling:
            self._last = None
        limit = overshoot_limit(ceiling)
        over = float(watts) > limit
        episode = self._episode
        if episode is not None and episode.target != dict(target):
            self._drop_episode()
            episode = None
        if episode is not None:
            if not over:
                episode.under_readings += 1
                if episode.under_readings >= RESTORE_READINGS:
                    self._resolve(now, episode, target, watts)
                return None
            episode.under_readings = 0
            episode.peak_w = max(episode.peak_w, float(watts))
            if now < episode.verify_until:
                return None
            if episode.method == REWRITE:
                episode.method = NUDGE
                episode.verify_until = now + VERIFY_S
                self._note("correcting", now, target, episode.peak_w, NUDGE)
                return NUDGE
            self._give_up(now, episode, target)
            return None
        if not over:
            self._over_since = None
            self._forget_unresolved()
            return None
        if (
            self._unresolved >= MAX_UNRESOLVED
            or self._restored_total >= MAX_RESTORED_PER_SESSION
            or now < self._cooldown_until
        ):
            return None
        if self._over_since is None or self._over_target != dict(target):
            self._over_since = now
            self._over_target = dict(target)
            self._over_peak = 0.0
            self._severe_since = None
        self._over_peak = max(self._over_peak, float(watts))
        severe_limit = max(
            ceiling * SEVERE_RATIO,
            int(target.get("pl3", ceiling)) * (1 + MARGIN_RATIO),
        )
        if float(watts) > severe_limit:
            if self._severe_since is None:
                self._severe_since = now
        else:
            self._severe_since = None
        severe = (
            self._severe_since is not None
            and now - self._severe_since >= SEVERE_SUSTAIN_S
        )
        if now - self._over_since < SUSTAIN_S and not severe:
            return None
        self._episode = _Episode(
            self._preferred,
            dict(target),
            now + VERIFY_S,
            self._over_peak,
        )
        self._note("correcting", now, target, self._over_peak, self._preferred)
        return self._preferred

    def _forget_unresolved(self):
        if self._last is not None and self._last["state"] == "unresolved":
            self._last = None

    def _drop_episode(self):
        self._episode = None
        if self._last is not None and self._last["state"] == "correcting":
            self._last = None

    def _resolve(self, now, episode, target, watts):
        self._episode = None
        self._over_since = None
        self._preferred = episode.method
        self._unresolved = 0
        self._restored_total += 1
        self._note(
            "restored",
            now,
            target,
            episode.peak_w,
            episode.method,
            settled_w=float(watts),
        )

    def _give_up(self, now, episode, target):
        self._episode = None
        self._over_since = None
        index = min(self._unresolved, len(UNRESOLVED_COOLDOWN_S) - 1)
        self._unresolved += 1
        self._cooldown_until = now + UNRESOLVED_COOLDOWN_S[index]
        self._note("unresolved", now, target, episode.peak_w, episode.method)

    def _note(self, state, now, target, peak_w, method, settled_w=None):
        self._last = {
            "state": state,
            "at": round(now, 3),
            "target_w": int(target["pl1"]),
            "ceiling_w": sustained_ceiling(target),
            "peak_w": round(peak_w, 1),
            "method": method,
            "settled_w": None if settled_w is None else round(settled_w, 1),
        }

    @property
    def last(self):
        return None if self._last is None else dict(self._last)

    def as_dict(self):
        return {
            "last": self.last,
            "correcting": self._episode is not None,
            "preferred_method": self._preferred,
            "unresolved": self._unresolved,
            "restored_total": self._restored_total,
        }
