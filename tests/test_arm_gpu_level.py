import asyncio
import os

from tdp.arm_levels import ArmPerformanceLevels
from test_gpu_clock_rpc import _make_plugin
from test_tdp_arm_levels import _caps, _thor


def _arm_plugin(tmp_path, monkeypatch):
    import tdp.factory as factory

    p, _ = _make_plugin(tmp_path, monkeypatch)
    root = _thor(tmp_path / "sys-root")
    monkeypatch.setattr(
        factory, "select_backend", lambda device, **kw: ArmPerformanceLevels(root=root)
    )
    p._init()
    return p, root


def test_backend_split_keeps_the_gpu_high_while_the_cpu_drops(tmp_path):
    root = _thor(tmp_path)
    backend = ArmPerformanceLevels(root=root)
    backend.set_split_gpu_level(10)
    assert backend.set_tdp(1, ac=False).ok is True
    assert _caps(root) == (787200, 1056000, 1248000, 680000000)
    assert backend.read_applied() == 1


def test_backend_split_lets_the_gpu_drop_alone(tmp_path):
    root = _thor(tmp_path)
    backend = ArmPerformanceLevels(root=root)
    backend.set_split_gpu_level(1)
    assert backend.set_tdp(10, ac=False).ok is True
    assert _caps(root) == (2016000, 2803200, 3187200, 220000000)
    assert backend.read_applied() == 10


def test_backend_readback_catches_a_gpu_ceiling_overwritten_by_another_owner(tmp_path):
    root = _thor(tmp_path)
    backend = ArmPerformanceLevels(root=root)
    backend.set_split_gpu_level(1)
    assert backend.set_tdp(10, ac=False).ok is True
    with open(f"{root}/sys/class/devfreq/3d00000.gpu/max_freq", "w") as node:
        node.write("680000000")
    assert backend.read_applied() is None


def test_gpu_starts_linked_and_moves_with_the_cpu(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    state = asyncio.run(p.get_tdp_state())
    assert state["gpu_level_supported"] is True
    assert state["gpu_level"] is None

    asyncio.run(p.set_tdp_watts(3, "global", None))
    assert _caps(root)[3] == 348000000


def test_unlinked_gpu_stays_put_when_the_cpu_level_changes(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    res = asyncio.run(p.set_gpu_level(10, "global", None))
    assert res["ok"] is True

    asyncio.run(p.set_tdp_watts(1, "global", None))
    assert _caps(root) == (787200, 1056000, 1248000, 680000000)
    state = asyncio.run(p.get_tdp_state())
    assert (state["global_watts"], state["global_gpu_level"]) == (1, 10)


def test_linking_again_puts_the_gpu_back_on_the_cpu_level(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_tdp_watts(3, "global", None))
    asyncio.run(p.set_gpu_level(10, "global", None))
    assert _caps(root)[3] == 680000000

    asyncio.run(p.set_gpu_level(None, "global", None))
    assert _caps(root)[3] == 348000000
    assert asyncio.run(p.get_tdp_state())["global_gpu_level"] is None


def test_auto_keeps_the_distance_between_cpu_and_gpu(tmp_path, monkeypatch):
    p, _ = _arm_plugin(tmp_path, monkeypatch)
    p._tdp_profiles.set_pl1("global", 3)
    p._tdp_profiles.set_gpu_level("global", 7)
    limits = p._limits()

    assert p._split_gpu_target(5, limits, 10) == 9
    assert p._split_gpu_target(8, limits, 10) == 10
    assert p._split_gpu_target(None, limits, 10) == 7


def test_eco_never_splits_so_both_drop_to_the_floor(tmp_path, monkeypatch):
    p, _ = _arm_plugin(tmp_path, monkeypatch)
    p._tdp_profiles.set_gpu_level("global", 10)
    p._settings["eco_enabled"] = True
    assert p._split_gpu_target(None, p._limits(), 10) is None


def test_new_game_profile_inherits_the_global_split(tmp_path, monkeypatch):
    p, _ = _arm_plugin(tmp_path, monkeypatch)
    p._tdp_profiles.set_gpu_level("global", 9)
    p._tdp_profiles.set_pl1("game", 4, appid="77")
    assert p._tdp_profiles.gpu_level("77") == 9
    assert p._game_profile_row("77")["tdp"]["gpu_level"] == 9


def test_gpu_card_reports_the_level_power_applies(tmp_path, monkeypatch):
    p, _ = _arm_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_tdp_watts(4, "global", None))
    asyncio.run(p.set_gpu_level(8, "global", None))
    state = p._gpu_clock_state()
    assert state["managed_by_power"] is True
    assert (state["power_level"], state["power_level_split"]) == (8, True)


def test_pc_backends_never_offer_a_gpu_level(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    p._init()
    state = asyncio.run(p.get_tdp_state())
    assert state["gpu_level_supported"] is False
    assert state["gpu_level"] is None
    res = asyncio.run(p.set_gpu_level(5, "global", None))
    assert res["detail"] == "gpu-level-unsupported"


def test_release_forgets_the_split_so_readback_sees_the_lifted_ceilings(tmp_path):
    root = _thor(tmp_path)
    backend = ArmPerformanceLevels(root=root)
    backend.set_split_gpu_level(5)
    assert backend.set_tdp(3, ac=False).ok is True
    assert backend.release() is True
    assert backend.split_gpu_level is None
    assert backend.read_applied() == 10


def test_auto_keeps_the_gpu_inside_the_players_auto_range(tmp_path, monkeypatch):
    p, _ = _arm_plugin(tmp_path, monkeypatch)
    p._tdp_profiles.set_pl1("global", 3)
    p._tdp_profiles.set_gpu_level("global", 6)
    p._tdp_profiles.set_auto_config("global", 40, 3, min_tdp=2, max_tdp=6)
    assert p._split_gpu_target(5, p._limits(), 10) == 6
    assert p._split_gpu_target(1, p._limits(), 10) == 4


def test_gpu_card_does_not_call_an_eco_floor_its_own_level(tmp_path, monkeypatch):
    p, _ = _arm_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_gpu_level(9, "global", None))
    p._settings["eco_enabled"] = True
    asyncio.run(p._apply_tdp_now("eco"))
    state = p._gpu_clock_state()
    assert state["power_level_split"] is False
    assert state["power_level"] == 1


def test_pc_journal_fingerprint_has_no_gpu_level(tmp_path, monkeypatch):
    p, _ = _make_plugin(tmp_path, monkeypatch)
    p._init()
    asyncio.run(p.set_tdp_watts(12, "global", None))
    assert all("gpu_level" not in event for event in p._tdp_history)


def test_backend_flags_a_foreign_write_to_the_split_gpu_cap(tmp_path):
    root = _thor(tmp_path)
    backend = ArmPerformanceLevels(root=root)
    backend.set_split_gpu_level(1)
    assert backend.set_tdp(10, ac=False).ok is True
    assert backend.split_gpu_drifted() is False
    with open(f"{root}/sys/class/devfreq/3d00000.gpu/max_freq", "w") as node:
        node.write("680000000")
    assert backend.split_gpu_drifted() is True


def test_failed_write_never_advertises_the_requested_gpu_level(tmp_path):
    root = _thor(tmp_path)
    backend = ArmPerformanceLevels(root=root)
    backend.set_split_gpu_level(10)
    assert backend.set_tdp(3, ac=False).ok is True
    assert backend.applied_split_gpu_level == 10
    os.chmod(f"{root}/sys/class/devfreq/3d00000.gpu/max_freq", 0o444)
    try:
        backend.set_split_gpu_level(1)
        backend.set_tdp(3, ac=False)
    finally:
        os.chmod(f"{root}/sys/class/devfreq/3d00000.gpu/max_freq", 0o644)
    assert backend.applied_split_gpu_level is None


def test_guard_reasserts_a_drifted_split_gpu_at_most_every_ten_seconds(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_gpu_level(1, "global", None))
    with open(f"{root}/sys/class/devfreq/3d00000.gpu/max_freq", "w") as node:
        node.write("680000000")
    assert p._gpu_split_reassert_due(100.0) is True
    assert p._gpu_split_reassert_due(105.0) is False
    assert p._gpu_split_reassert_due(111.0) is True


def test_guard_tick_restores_a_split_gpu_cap_after_it_was_confirmed(tmp_path, monkeypatch):
    p, root = _arm_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_tdp_watts(10, "global", None))
    asyncio.run(p.set_gpu_level(1, "global", None))
    p._tdp_guard_tick(1000.0)
    assert _caps(root)[3] == 220000000
    with open(f"{root}/sys/class/devfreq/3d00000.gpu/max_freq", "w") as node:
        node.write("680000000")
    p._tdp_guard_tick(1003.0)
    assert _caps(root)[3] == 220000000
    assert p._tdp_history[-1]["action"] == "gpu-split-reassert"
