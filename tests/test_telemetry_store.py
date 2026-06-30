import os

import pytest

from telemetry.store import TelemetryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(tmp_path):
    return TelemetryStore(str(tmp_path / "telemetry.json"))


def _sample(pl1=15, watts=12.5, gpu=80, t_cpu=55.0, t_gpu=50.0, rpm=2000):
    return {
        "pl1": pl1,
        "watts": watts,
        "gpu_busy": gpu,
        "temp_cpu": t_cpu,
        "temp_gpu": t_gpu,
        "fan_rpm": rpm,
    }


# ---------------------------------------------------------------------------
# Unknown / empty appid
# ---------------------------------------------------------------------------

def test_aggregate_unknown_appid_returns_empty(tmp_path):
    s = _store(tmp_path)
    agg = s.aggregate("999")
    assert agg == {"samples_n": 0, "by_pl1": {}, "recent": []}


# ---------------------------------------------------------------------------
# Binning by pl1
# ---------------------------------------------------------------------------

def test_add_sample_bins_by_integer_pl1(tmp_path):
    s = _store(tmp_path)
    s.add_sample("1", _sample(pl1=15), dt=5.0)
    s.add_sample("1", _sample(pl1=15), dt=5.0)
    s.add_sample("1", _sample(pl1=20), dt=5.0)
    agg = s.aggregate("1")
    assert agg["samples_n"] == 3
    assert set(agg["by_pl1"].keys()) == {15, 20}
    assert agg["by_pl1"][15]["seconds"] == pytest.approx(10.0)
    assert agg["by_pl1"][20]["seconds"] == pytest.approx(5.0)


def test_bins_keyed_by_int_not_string(tmp_path):
    s = _store(tmp_path)
    s.add_sample("1", _sample(pl1=15), dt=5.0)
    agg = s.aggregate("1")
    key = next(iter(agg["by_pl1"].keys()))
    assert isinstance(key, int)


# ---------------------------------------------------------------------------
# Averages
# ---------------------------------------------------------------------------

def test_averages_computed_correctly(tmp_path):
    s = _store(tmp_path)
    s.add_sample("1", _sample(pl1=15, watts=10.0, gpu=80, t_cpu=50.0, t_gpu=45.0, rpm=1800), dt=5.0)
    s.add_sample("1", _sample(pl1=15, watts=14.0, gpu=90, t_cpu=60.0, t_gpu=55.0, rpm=2200), dt=5.0)
    agg = s.aggregate("1")
    b = agg["by_pl1"][15]
    assert b["watts_avg"] == pytest.approx(12.0)
    assert b["gpu_avg"] == pytest.approx(85.0)
    assert b["temp_cpu_avg"] == pytest.approx(55.0)
    assert b["temp_gpu_avg"] == pytest.approx(50.0)
    assert b["rpm_avg"] == pytest.approx(2000.0)


# ---------------------------------------------------------------------------
# None metrics — honest: None avg when n==0; don't poison present metrics
# ---------------------------------------------------------------------------

def test_none_metric_yields_none_avg_and_does_not_poison_others(tmp_path):
    s = _store(tmp_path)
    # All Nones for watts/gpu/temps/rpm
    s.add_sample("1", {"pl1": 15, "watts": None, "gpu_busy": None,
                        "temp_cpu": None, "temp_gpu": None, "fan_rpm": None}, dt=5.0)
    agg = s.aggregate("1")
    b = agg["by_pl1"][15]
    assert b["watts_avg"] is None
    assert b["gpu_avg"] is None
    assert b["temp_cpu_avg"] is None
    assert b["temp_gpu_avg"] is None
    assert b["rpm_avg"] is None


def test_partial_none_only_poisons_missing_metric(tmp_path):
    s = _store(tmp_path)
    s.add_sample("1", _sample(pl1=15, watts=12.0, gpu=None, t_cpu=50.0, t_gpu=45.0, rpm=2000), dt=5.0)
    agg = s.aggregate("1")
    b = agg["by_pl1"][15]
    assert b["watts_avg"] == pytest.approx(12.0)
    assert b["gpu_avg"] is None   # never had a real value
    assert b["temp_cpu_avg"] == pytest.approx(50.0)


def test_none_then_real_value_averages_only_real(tmp_path):
    s = _store(tmp_path)
    s.add_sample("1", _sample(pl1=15, watts=None), dt=5.0)
    s.add_sample("1", _sample(pl1=15, watts=10.0), dt=5.0)
    agg = s.aggregate("1")
    b = agg["by_pl1"][15]
    # Only 1 real sample for watts
    assert b["watts_avg"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Recent ring buffer
# ---------------------------------------------------------------------------

def test_recent_ring_capped_at_120(tmp_path):
    s = _store(tmp_path)
    for i in range(130):
        s.add_sample("1", _sample(pl1=15), dt=5.0, ts=float(i))
    agg = s.aggregate("1")
    assert len(agg["recent"]) == 120


def test_recent_oldest_dropped(tmp_path):
    s = _store(tmp_path)
    for i in range(130):
        s.add_sample("1", _sample(pl1=15), dt=5.0, ts=float(i))
    agg = s.aggregate("1")
    # ts values should be 10..129 (oldest 0..9 dropped)
    tss = [r["ts"] for r in agg["recent"]]
    assert tss[0] == pytest.approx(10.0)
    assert tss[-1] == pytest.approx(129.0)


def test_recent_entry_shape(tmp_path):
    s = _store(tmp_path)
    s.add_sample("1", _sample(pl1=15, watts=12.0, gpu=80, t_cpu=55.0, t_gpu=50.0, rpm=2000),
                 dt=5.0, ts=1000.0)
    agg = s.aggregate("1")
    entry = agg["recent"][0]
    assert entry["ts"] == pytest.approx(1000.0)
    assert entry["pl1"] == 15
    assert entry["watts"] == pytest.approx(12.0)
    assert entry["gpu"] == 80
    assert entry["t_cpu"] == pytest.approx(55.0)
    assert entry["t_gpu"] == pytest.approx(50.0)
    assert entry["rpm"] == pytest.approx(2000.0)


# ---------------------------------------------------------------------------
# Game cap at 50
# ---------------------------------------------------------------------------

def test_prunes_oldest_game_when_over_50(tmp_path):
    s = _store(tmp_path)
    # Add 51 games in order; game "0" is the oldest
    for i in range(51):
        s.add_sample(str(i), _sample(pl1=15), dt=5.0, ts=float(i))
    agg_old = s.aggregate("0")
    assert agg_old["samples_n"] == 0  # pruned


def test_keeps_most_recent_50_games(tmp_path):
    s = _store(tmp_path)
    for i in range(51):
        s.add_sample(str(i), _sample(pl1=15), dt=5.0, ts=float(i))
    # games 1..50 should survive
    for i in range(1, 51):
        assert s.aggregate(str(i))["samples_n"] == 1


# ---------------------------------------------------------------------------
# Persist and reload
# ---------------------------------------------------------------------------

def test_persists_and_reloads(tmp_path):
    path = str(tmp_path / "telemetry.json")
    s1 = TelemetryStore(path)
    s1.add_sample("42", _sample(pl1=15, watts=12.0), dt=5.0, ts=100.0)
    s1.flush()  # writes are buffered; flush persists
    s2 = TelemetryStore(path)
    agg = s2.aggregate("42")
    assert agg["samples_n"] == 1
    assert agg["by_pl1"][15]["watts_avg"] == pytest.approx(12.0)
    assert len(agg["recent"]) == 1


# ---------------------------------------------------------------------------
# Write throttling: add_sample buffers in memory; flush() persists.
# ---------------------------------------------------------------------------

def test_add_sample_does_not_write_until_flush(tmp_path):
    path = str(tmp_path / "telemetry.json")
    s = TelemetryStore(path)
    s.add_sample("1", _sample(pl1=15), dt=5.0)
    assert not os.path.exists(path)  # throttled — no per-sample disk write
    s.flush()
    assert os.path.exists(path)


def test_flush_is_noop_when_nothing_changed(tmp_path):
    path = str(tmp_path / "telemetry.json")
    s = TelemetryStore(path)
    s.flush()  # nothing buffered → no file, no error
    assert not os.path.exists(path)


def test_aggregate_reflects_unflushed_samples(tmp_path):
    # In-session reads (RPC/F3) must see buffered data without a flush.
    s = _store(tmp_path)
    s.add_sample("1", _sample(pl1=15), dt=5.0)
    assert s.aggregate("1")["samples_n"] == 1


# ---------------------------------------------------------------------------
# Corrupt file → empty store (never raises)
# ---------------------------------------------------------------------------

def test_corrupt_json_file_returns_empty_store(tmp_path):
    path = tmp_path / "telemetry.json"
    path.write_text("{ not valid json !!!")
    s = TelemetryStore(str(path))
    agg = s.aggregate("1")
    assert agg == {"samples_n": 0, "by_pl1": {}, "recent": []}


def test_add_sample_never_raises_on_bad_data(tmp_path):
    s = _store(tmp_path)
    # Missing keys, wrong types — must not raise
    s.add_sample("1", {}, dt=5.0)
    s.add_sample("1", {"pl1": "not-an-int"}, dt=5.0)
