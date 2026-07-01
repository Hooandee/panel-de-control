"""G2 suggestion brain — turn a game's per-PL1 telemetry into a learned TDP band.

Pure functions, no I/O. Mirror of ``fans/suggest.py`` but for power: instead of a
fan curve we derive a ``[floor, ceil]`` watt band + a habitual ``seed`` for the
live auto-TDP loop to operate within, plus a dial that picks the resting target
inside that band (battery ↔ performance).

The honest contract: we can only infer a band once we've actually observed the
game at **several PL1 levels** for long enough — otherwise ``enough`` is False and
the caller falls back to the device's full range (never a fabricated band).

Floor honesty is GPU-PRIMARY (``_satisfied``), matching the honest signal the
control loop acts on. A PL1 level "had headroom" when the GPU was NOT saturated
there (``gpu_avg < _GPU_STARVED``). On a power-limited game the draw just follows
PL1, so watts/boost are confounded — they can't tell "has margin" from "needs it"
(measured on-device: 35 W cap / 80% GPU looked "no headroom" by watts, yet 80%
GPU means there IS margin). GPU utilisation is the only honest "could it go lower?"
signal, so the learned floor and the loop's knee converge on the same PL1. A level
that pinned the GPU is power-limited, not satisfied — so it can never be the floor.
watts/boost remain only as fallbacks for a device with no GPU% reading.
"""

# Gating — don't infer a band until we've seen real, varied usage.
_MIN_BIN_SECONDS = 60      # ignore transient PL1 bins (brief visits)
_MIN_SECONDS = 1800        # ~30 min of in-game dwell across kept bins
MIN_MINUTES = _MIN_SECONDS // 60   # learning-progress target (minutes), for the UI

# A level is "satisfied" when its real draw is below this fraction of its budget
# (the game had headroom — that power was enough). At/above it the level is
# power-limited (drew ~everything), i.e. the game was still hungry there.
_HEADROOM_FRAC = 0.90

# GPU-saturation threshold (busy %) — the PRIMARY honest signal. >= this = pinned
# ~100%, the game still wants more power (not satisfied / power-limited). Aligns
# with the control loop's up-trigger so the learned floor and the knee converge.
_GPU_STARVED = 97


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _unavail(reason, lo=None, hi=None):
    return {"floor": None, "ceil": None, "seed": None,
            "observed_lo": lo, "observed_hi": hi,
            "enough": False, "reason": reason}


def learned_band(by_pl1: dict) -> dict:
    """Derive a learned TDP band from a game's ``by_pl1`` aggregate.

    *by_pl1*: ``{pl1(int): {"seconds": float, "gpu_avg": float|None, ...}}``.

    Returns ``{"floor", "ceil", "seed", "observed_lo", "observed_hi", "enough",
    "reason"}``. When ``enough`` is False (reason ∈ {no_data, too_few, one_level})
    the band fields are None and the caller must fall back to the device's full
    range — but ``observed_lo``/``observed_hi`` (min/max PL1 actually seen) are
    populated whenever any real dwell exists, for an honest "still learning" display.
    """
    # Keep only bins with real dwell and at least one usable signal (watts or GPU).
    bins = {
        int(pl1): row for pl1, row in by_pl1.items()
        if row.get("seconds", 0) >= _MIN_BIN_SECONDS
        and (row.get("watts_avg") is not None or row.get("gpu_avg") is not None)
    }
    if not bins:
        return _unavail("no_data")

    levels = sorted(bins)
    obs_lo, obs_hi = levels[0], levels[-1]

    total = sum(row["seconds"] for row in bins.values())
    if total < _MIN_SECONDS:
        return _unavail("too_few", obs_lo, obs_hi)
    if len(bins) < 2:
        return _unavail("one_level", obs_lo, obs_hi)

    # ceil = the most it actually ran at (highest dwell-bearing level).
    ceil = obs_hi
    # floor = the lowest PL1 with REAL HEADROOM (see _satisfied). Fall back to ceil
    # when it was hungry everywhere ("wants at least the most it ever got"). Every
    # satisfied level is in `levels` (all <= ceil), so floor <= ceil holds already.
    floor = next((pl1 for pl1 in levels if _satisfied(pl1, bins[pl1])), ceil)

    # seed = habitual setpoint (most dwell), clamped into the band.
    seed = max(levels, key=lambda pl1: bins[pl1]["seconds"])
    seed = _clamp(seed, floor, ceil)

    return {"floor": floor, "ceil": ceil, "seed": seed,
            "observed_lo": obs_lo, "observed_hi": obs_hi,
            "enough": True, "reason": "ok"}


def _satisfied(pl1: int, row: dict) -> bool:
    """True when *pl1* had real headroom for the game (not power-limited).

    GPU-PRIMARY, matching the honest signal the control loop acts on: a level had
    headroom when the GPU was NOT saturated there (``gpu_avg < _GPU_STARVED``). On
    a power-limited game the draw just follows PL1, so watts is confounded (it can't
    tell "has margin" from "needs it") — GPU utilisation is the only honest "could
    it go lower?" signal, so the learned floor and the loop's knee converge. The
    watts test stays ONLY as a fallback for a device with no GPU% reading (boost is
    derived from watts, so it can never be the sole signal — no boost branch here).
    """
    gpu = row.get("gpu_avg")
    if gpu is not None:
        return gpu < _GPU_STARVED
    watts = row.get("watts_avg")
    return watts is not None and watts < pl1 * _HEADROOM_FRAC
