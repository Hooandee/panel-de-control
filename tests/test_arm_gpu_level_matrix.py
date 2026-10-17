import asyncio
import itertools

import pytest

from test_arm_gpu_level import _arm_plugin
from test_tdp_arm_levels import _caps


def _expected(p, cpu, gpu):
    cpu_caps = p._tdp_backend.ceilings(cpu)
    gpu_caps = p._tdp_backend.ceilings(cpu if gpu is None else gpu)
    return (*cpu_caps[:3], gpu_caps[3])


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("cpu,gpu", list(itertools.product(range(1, 11), [None, *range(1, 11)])))
def test_every_cpu_and_gpu_pair_lands_on_the_hardware(tmp_path, monkeypatch, cpu, gpu):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    assert _run(p.set_tdp_watts(cpu, "global", None))["ok"] is True
    assert _run(p.set_gpu_level(gpu, "global", None))["ok"] is True
    assert _caps(root) == _expected(p, cpu, gpu)
    state = _run(p.get_tdp_state())
    assert (state["global_watts"], state["global_gpu_level"]) == (cpu, gpu)
    assert p._tdp_backend.read_applied() == cpu


@pytest.mark.parametrize("cpu,gpu", [(1, 10), (10, 1), (3, 3), (6, 9)])
def test_gpu_first_then_cpu_gives_the_same_caps(tmp_path, monkeypatch, cpu, gpu):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.set_gpu_level(gpu, "global", None))
    _run(p.set_tdp_watts(cpu, "global", None))
    assert _caps(root) == _expected(p, cpu, gpu)


def test_out_of_range_requests_are_clamped_not_written_raw(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.set_tdp_watts(4, "global", None))
    _run(p.set_gpu_level(42, "global", None))
    assert _run(p.get_tdp_state())["global_gpu_level"] == 10
    _run(p.set_gpu_level(-3, "global", None))
    assert _run(p.get_tdp_state())["global_gpu_level"] == 1
    assert _caps(root) == _expected(p, 4, 1)


def test_a_cpu_preset_leaves_a_split_gpu_alone(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.set_gpu_level(9, "global", None))
    _run(p.apply_power_preset(1, "global", None))
    assert _caps(root) == _expected(p, 1, 9)


def test_a_linked_preset_moves_both(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.apply_power_preset(3, "global", None))
    assert _caps(root) == _expected(p, 3, None)


def test_game_split_is_its_own_and_global_returns_on_game_exit(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.set_tdp_watts(6, "global", None))
    _run(p.set_gpu_level(2, "global", None))
    _run(p.set_current_game("77"))
    assert _caps(root) == _expected(p, 6, 2)

    _run(p.set_tdp_watts(3, "game", "77", "77"))
    assert _caps(root) == _expected(p, 3, 2)
    _run(p.set_gpu_level(10, "game", "77", "77"))
    assert _caps(root) == _expected(p, 3, 10)
    assert _run(p.get_tdp_state())["global_gpu_level"] == 2

    _run(p.set_current_game(None))
    assert _caps(root) == _expected(p, 6, 2)
    _run(p.set_current_game("77"))
    assert _caps(root) == _expected(p, 3, 10)


def test_following_global_again_applies_the_global_split(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.set_gpu_level(8, "global", None))
    _run(p.set_current_game("77"))
    _run(p.set_gpu_level(None, "game", "77", "77"))
    _run(p.set_tdp_watts(2, "game", "77", "77"))
    assert _caps(root) == _expected(p, 2, None)
    _run(p.set_tdp_follow_global(True, "77", "77"))
    global_cpu = _run(p.get_tdp_state())["global_watts"]
    assert _caps(root) == _expected(p, global_cpu, 8)


def test_a_stale_context_never_writes_the_gpu(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.set_current_game("77"))
    before = _caps(root)
    res = _run(p.set_gpu_level(1, "game", "99", "99"))
    assert res["detail"] == "stale-context"
    assert _caps(root) == before
    assert p._tdp_profiles.has_game("99") is False


def test_control_off_lifts_everything_and_on_restores_the_split(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.set_tdp_watts(3, "global", None))
    _run(p.set_gpu_level(9, "global", None))
    _run(p.set_tdp_control_enabled(False))
    assert _caps(root) == _expected(p, 10, None)
    assert _run(p.set_gpu_level(5, "global", None))["detail"] == "tdp-control-disabled"
    _run(p.set_tdp_control_enabled(True))
    assert _caps(root) == _expected(p, 3, 9)


def test_eco_drops_both_and_leaving_it_restores_the_split(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.set_tdp_watts(4, "global", None))
    _run(p.set_gpu_level(10, "global", None))
    _run(p.set_eco(True, 50))
    assert _caps(root)[3] == _expected(p, 1, None)[3]
    _run(p.set_eco(False, 50))
    assert _caps(root) == _expected(p, 4, 10)


def test_touching_the_gpu_level_leaves_eco(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.set_tdp_watts(4, "global", None))
    _run(p.set_eco(True, 50))
    _run(p.set_gpu_level(7, "global", None))
    assert p._settings.get("eco_enabled") is False
    assert _caps(root) == _expected(p, 4, 7)


def test_a_restart_reapplies_the_saved_split(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.set_tdp_watts(5, "global", None))
    _run(p.set_gpu_level(1, "global", None))
    restarted = type(p)()
    restarted._init()
    assert restarted._tdp_profiles.gpu_level(None) == 1
    _run(restarted._apply_tdp_now("startup"))
    assert _caps(root) == _expected(p, 5, 1)


@pytest.mark.parametrize("auto,cpu,gpu,auto_range,expected_gpu", [
    (5, 3, 6, (None, None), 8),
    (10, 3, 6, (None, None), 10),
    (1, 6, 3, (None, None), 1),
    (10, 4, 1, (None, None), 7),
    (5, 3, 6, (2, 6), 6),
    (2, 6, 3, (2, 8), 2),
    (7, 7, None, (None, None), None),
])
def test_auto_writes_the_gpu_at_the_players_distance(tmp_path, monkeypatch, auto, cpu, gpu, auto_range, expected_gpu):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    _run(p.set_tdp_watts(cpu, "global", None))
    _run(p.set_gpu_level(gpu, "global", None))
    p._tdp_profiles.set_auto_config("global", 40, cpu, min_tdp=auto_range[0], max_tdp=auto_range[1])
    monkeypatch.setattr(p, "_auto_runtime_active", lambda: True)
    p._auto_setpoint = auto
    res = _run(p._apply_tdp_now("auto-step", auto_watts=auto))
    assert res.ok is True
    assert _caps(root) == _expected(p, auto, expected_gpu)
