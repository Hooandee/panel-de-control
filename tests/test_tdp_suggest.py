from tdp import suggest as tdp_suggest
from tdp.suggest import learned_band


def _by_pl1(rows):
    """Build a by_pl1 aggregate from (pl1, seconds, gpu_avg[, watts_avg[, boost_avg]]).

    Mirrors TelemetryStore.aggregate()['by_pl1']: keyed by int pl1, each row has
    seconds + the *_avg metrics. learned_band's _satisfied is GPU-PRIMARY (a level
    "had headroom" when gpu_avg < _GPU_STARVED, the same honest signal the control
    loop acts on — watts is confounded on power-limited games where the draw just
    follows PL1). The watts test remains only as a fallback when GPU% is absent
    (boost_avg is kept as a telemetry column but is not a _satisfied signal). When
    a row omits its 4th/5th element that metric is None.
    """
    out = {}
    for row in rows:
        pl1, s, g = row[0], row[1], row[2]
        watts = row[3] if len(row) > 3 else None
        boost = row[4] if len(row) > 4 else None
        out[int(pl1)] = {
            "seconds": float(s),
            "gpu_avg": (None if g is None else float(g)),
            "watts_avg": (None if watts is None else float(watts)),
            "boost_avg": (None if boost is None else float(boost)),
            "temp_cpu_avg": None,
            "temp_gpu_avg": None,
            "rpm_avg": None,
        }
    return out


# A realistic distribution. _satisfied is GPU-PRIMARY: a level "had headroom" when
# gpu_avg < _GPU_STARVED (97); at/above that the GPU was pinned = still hungry.
# >=2 distinct levels, >30 min total dwell.
#   12 W: GPU 99 (pinned)  → starved
#   15 W: GPU 98 (pinned)  → starved
#   18 W: GPU 88 (< 97)    → SATISFIED (lowest satisfied) -> floor
#   21 W: GPU 80           → satisfied
#   24 W: GPU 70 (highest dwell-bearing level) -> ceil
def _good():
    return _by_pl1([
        (12, 600, 99, 11.8),
        (15, 700, 98, 14.7),
        (18, 800, 88, 15.0),   # habitual (most dwell) AND first satisfied -> floor & seed
        (21, 600, 80, 16.0),
        (24, 400, 70, 17.0),
    ])


# ---------------------------------------------------------------------------
# Gating (enough / reason) — honest degradation
# ---------------------------------------------------------------------------

def test_empty_is_no_data():
    b = learned_band({})
    assert b["enough"] is False
    assert b["reason"] == "no_data"
    assert b["floor"] is None and b["ceil"] is None and b["seed"] is None


def test_all_bins_below_min_dwell_is_no_data():
    # Transient bins (<60 s each) are ignored -> nothing left to learn from.
    b = learned_band(_by_pl1([(12, 30, 99), (15, 40, 90)]))
    assert b["enough"] is False
    assert b["reason"] == "no_data"


def test_single_level_is_one_level():
    b = learned_band(_by_pl1([(15, 2000, 90)]))
    assert b["enough"] is False
    assert b["reason"] == "one_level"


def test_below_30min_total_is_too_few():
    b = learned_band(_by_pl1([(12, 400, 99), (15, 400, 90)]))  # 800 s < 1800
    assert b["enough"] is False
    assert b["reason"] == "too_few"


def test_good_distribution_is_ok():
    b = learned_band(_good())
    assert b["enough"] is True
    assert b["reason"] == "ok"


# ---------------------------------------------------------------------------
# Band derivation — GPU-PRIMARY (the honest "was the GPU saturated here?" signal,
# matching the control loop — watts/boost are confounded on power-limited games)
# ---------------------------------------------------------------------------

def test_floor_is_lowest_unsaturated_pl1_by_gpu():
    # floor = lowest PL1 where gpu_avg < _GPU_STARVED (97) = had margin. In _good()
    # that's 18 W (GPU 88); 12/15 pinned the GPU (99/98 = power-limited).
    assert learned_band(_good())["floor"] == 18


def test_ceil_is_highest_pl1_with_real_dwell():
    # ceil = the most it actually ran at (highest dwell-bearing level) = 24.
    assert learned_band(_good())["ceil"] == 24


def test_seed_is_habitual_pl1_clamped_into_band():
    # most-dwell PL1 is 18, inside [18, 24]
    assert learned_band(_good())["seed"] == 18


def test_power_limited_low_pl1_never_becomes_floor():
    # The 7W-stuck bug, GPU-honest: at 7/17 W the GPU was PINNED (starved), only at
    # 22 W did it fall below saturation (had margin). floor MUST be 22, never 7 —
    # the honest signal is that the GPU had no headroom at the low levels.
    b = learned_band(_by_pl1([
        (7, 1000, 100, 7.0),   # GPU pinned → starved
        (17, 1100, 98, 17.0),  # GPU pinned → starved
        (22, 1000, 85, 19.0),  # GPU 85 < 97 → SATISFIED
    ]))
    assert b["enough"] is True
    assert b["floor"] == 22
    assert b["ceil"] == 22  # highest dwell-bearing level
    assert b["floor"] <= b["ceil"]


def test_power_limited_at_cap_but_gpu_has_margin_is_satisfied():
    # THE on-device case (Ally, 35 W cap / 80% GPU / draw pinned): watts says "no
    # headroom" (draw==cap) but the GPU at 80% had margin → GPU-primary marks it
    # SATISFIED, so a lower level with margin becomes the floor rather than the cap.
    b = learned_band(_by_pl1([
        (25, 900, 96, 25.0, 0.9),  # GPU near-pinned (96 < 97 just barely) — satisfied
        (30, 900, 88, 30.0, 0.9),  # GPU 88 → satisfied
        (35, 900, 80, 35.0, 0.9),  # cap, GPU 80 → satisfied (has margin!)
    ]))
    assert b["enough"] is True
    assert b["floor"] == 25   # lowest with GPU margin, NOT the 35 W cap
    assert b["ceil"] == 35


def test_clean_knee_floor_below_ceil():
    # A clean case: satisfied from 18 up, observed up to 24.
    b = learned_band(_by_pl1([
        (12, 700, 99, 11.9),   # starved
        (18, 800, 88, 15.0),   # SATISFIED → floor
        (24, 700, 70, 16.0),   # satisfied, highest level → ceil
    ]))
    assert b["floor"] == 18
    assert b["ceil"] == 24
    assert b["floor"] < b["ceil"]


def test_hungry_everywhere_floor_equals_ceil_equals_max():
    # Power-limited at EVERY observed level (drew ~all its budget) → the game wants
    # at least the most it ever got: floor == ceil == max(observed).
    b = learned_band(_by_pl1([
        (12, 1000, 100, 11.9),
        (15, 1100, 99, 14.8),
        (18, 1000, 98, 17.8),
    ]))
    assert b["enough"] is True
    assert b["floor"] == 18
    assert b["ceil"] == 18
    assert b["seed"] == 18


def test_seed_clamped_up_into_band():
    # habitual PL1 (12, most dwell) sits below the learned floor -> clamp to floor
    b = learned_band(_by_pl1([
        (12, 1500, 99, 11.9),  # most dwell but starved
        (18, 700, 88, 15.0),   # SATISFIED → floor
        (21, 700, 80, 16.0),
        (24, 700, 70, 17.0),
    ]))
    assert b["floor"] == 18
    assert b["seed"] == 18


def test_transient_bins_ignored_but_real_ones_kept():
    b = learned_band(_by_pl1([
        (9, 30, 100, 8.9),    # transient (<60 s), dropped
        (15, 700, 98, 14.8),  # GPU pinned → starved
        (18, 800, 88, 15.0),  # GPU 88 → SATISFIED → floor
        (21, 700, 80, 16.0),  # highest dwell-bearing → ceil
    ]))
    assert b["enough"] is True
    assert b["floor"] == 18
    assert b["ceil"] == 21


# ---------------------------------------------------------------------------
# GPU-only rows (primary path): floor = lowest PL1 with gpu_avg < _GPU_STARVED
# ---------------------------------------------------------------------------

def _gpu_only():
    #   12: 99 pinned; 15: 96 (first <97) -> floor; 24: highest dwell -> ceil
    return _by_pl1([
        (12, 600, 99),
        (15, 700, 96),
        (18, 800, 88),
        (21, 600, 80),
        (24, 400, 70),
    ])


def test_gpu_floor_is_lowest_unsaturated():
    b = learned_band(_gpu_only())
    assert b["enough"] is True
    assert b["floor"] == 15   # first PL1 with gpu_avg < 97 (had margin)
    assert b["ceil"] == 24    # ceil is always the highest dwell-bearing level


def test_gpu_saturated_everywhere_collapses_to_max():
    # GPU pinned at every level → hungry everywhere → floor==ceil==max.
    b = learned_band(_by_pl1([(12, 1000, 100), (15, 1100, 99), (18, 1000, 98)]))
    assert b["enough"] is True
    assert b["floor"] == 18
    assert b["ceil"] == 18


def test_bins_with_no_gpu_or_watts_signal_ignored():
    # A bin with neither watts nor gpu can't be reasoned about → ignored entirely.
    b = learned_band(_by_pl1([(12, 700, None), (15, 700, 96), (18, 800, 88), (21, 700, 80)]))
    assert b["floor"] == 15  # gpu-only fallback; the None bin doesn't count


# ---------------------------------------------------------------------------
# GPU-PRIMARY wins over the (confounded) watts/boost signals. On a power-limited
# game the draw follows PL1, so watts_avg > PL1 and boost is chronic everywhere —
# yet the GPU can still have margin. GPU utilisation decides; watts/boost are only
# fallbacks when GPU% is absent. (This is why the "34-34"/"stuck at max" bug dies.)
# ---------------------------------------------------------------------------

def test_gpu_wins_over_confounded_watts_and_boost():
    # Ally-style: draw >= PL1 everywhere (watts "starved"), boost chronic — the
    # watts/boost view would collapse to max. But GPU shows real margin from 18 up:
    #   12 W: GPU 99 pinned → starved
    #   15 W: GPU 98 pinned → starved
    #   18 W: GPU 90 (< 97) → SATISFIED → floor (despite watts/boost saying starved)
    #   22 W: GPU 82, highest dwell-bearing → ceil
    b = learned_band(_by_pl1([
        (12, 700, 99, 14.0, 0.95),
        (15, 800, 98, 17.0, 0.80),
        (18, 900, 90, 19.0, 0.90),  # watts>PL1, boost chronic, but GPU has margin
        (22, 600, 82, 20.0, 0.90),
    ]))
    assert b["enough"] is True
    assert b["floor"] == 18   # GPU-primary, ignoring the confounded watts/boost
    assert b["ceil"] == 22


def test_gpu_pinned_everywhere_collapses_to_max():
    # Truly power-bound: GPU pinned at every level → hungry everywhere → floor ==
    # ceil == max observed (honest, not a fake low floor from watts/boost).
    b = learned_band(_by_pl1([
        (18, 900, 99, 22.0, 0.9),
        (25, 900, 98, 30.0, 0.85),
        (35, 900, 97, 42.0, 0.8),
    ]))
    assert b["enough"] is True
    assert b["floor"] == 35
    assert b["ceil"] == 35


def test_no_gpu_falls_back_to_watts():
    # No GPU% (device without gpu_busy but with watts) → watts test is the fallback.
    b = learned_band(_by_pl1([
        (12, 700, None, 11.8),   # watts ~98% → starved
        (18, 800, None, 15.0),   # watts 83% → SATISFIED
        (24, 400, None, 17.0),
    ]))
    assert b["floor"] == 18   # watts fallback when GPU is absent


# ---------------------------------------------------------------------------
# Observed range (for the "learning" display) + minutes target
# ---------------------------------------------------------------------------

def test_observed_range_spans_kept_bins_even_when_not_enough():
    # One level, <30 min → not enough, but we still observed a PL1 to show.
    b = learned_band(_by_pl1([(15, 400, 90)]))
    assert b["enough"] is False
    assert b["observed_lo"] == 15
    assert b["observed_hi"] == 15


def test_observed_range_uses_min_and_max_of_kept_bins():
    b = learned_band(_good())
    assert b["observed_lo"] == 12
    assert b["observed_hi"] == 24


def test_observed_range_ignores_transient_bins():
    b = learned_band(_by_pl1([(9, 30, 100), (15, 700, 96), (21, 700, 80)]))
    assert b["observed_lo"] == 15  # the 9 W transient (<60 s) is dropped
    assert b["observed_hi"] == 21


def test_observed_range_none_when_no_data():
    b = learned_band({})
    assert b["observed_lo"] is None and b["observed_hi"] is None


def test_min_minutes_is_30():
    assert tdp_suggest.MIN_MINUTES == 30
