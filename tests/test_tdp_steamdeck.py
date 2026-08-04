import os

import tdp.steamdeck_hwmon as deck_module
from tdp.steamdeck_hwmon import SteamDeckHwmonBackend
from tdp.types import TdpLimits


FALLBACK = TdpLimits(min_w=3, default_w=12, max_w=15, max_ac_w=15)


def _write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(str(value))


def _mk_hwmon(
    root,
    idx=7,
    *,
    name="amdgpu",
    slow=15,
    fast=15,
    include_fast=True,
    slow_label="slowPPT",
    fast_label="fastPPT",
    maxima=False,
):
    directory = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    _write(os.path.join(directory, "name"), name)
    _write(os.path.join(directory, "power1_cap"), slow * 1_000_000)
    if slow_label is not None:
        _write(os.path.join(directory, "power1_label"), slow_label)
    if include_fast:
        _write(os.path.join(directory, "power2_cap"), fast * 1_000_000)
        if fast_label is not None:
            _write(os.path.join(directory, "power2_label"), fast_label)
    if maxima:
        _write(os.path.join(directory, "power1_cap_min"), 3_000_000)
        _write(os.path.join(directory, "power1_cap_max"), 29_000_000)
        _write(os.path.join(directory, "power2_cap_min"), 3_000_000)
        _write(os.path.join(directory, "power2_cap_max"), 30_000_000)
    return directory


def _backend(root, key="steam_deck_lcd"):
    return SteamDeckHwmonBackend(FALLBACK, key, root=str(root))


def test_exact_deck_discovers_shuffled_amdgpu_pair_and_compatibility_limits(tmp_path):
    _mk_hwmon(str(tmp_path), 0, name="nvme")
    _mk_hwmon(str(tmp_path), 9)

    backend = _backend(tmp_path, "steam_deck_oled")

    assert backend.supported is True
    assert backend.ppt_capability() == {
        "supported": True,
        "source": "compatibility_override",
        "slow": {"min": 3, "max": 29},
        "fast": {"min": 3, "max": 30},
        "visual_max": 30,
    }


def test_authoritative_sysfs_maxima_are_preferred(tmp_path):
    _mk_hwmon(str(tmp_path), maxima=True, slow_label=None, fast_label=None)

    capability = _backend(tmp_path).ppt_capability()

    assert capability["supported"] is True
    assert capability["source"] == "sysfs"
    assert capability["slow"]["max"] == 29
    assert capability["fast"]["max"] == 30


def test_power1_only_keeps_safe_base_control_without_advanced_ppt(tmp_path):
    cap = os.path.join(_mk_hwmon(str(tmp_path), include_fast=False), "power1_cap")
    backend = _backend(tmp_path)

    assert backend.supported is True
    assert backend.ppt_capability()["supported"] is False
    result = backend.set_tdp(12, ac=False)
    assert result.ok is True and result.applied_w == 12
    assert open(cap).read().strip() == "12000000"


def test_complete_ppt_surface_wins_over_earlier_base_only_surface(tmp_path):
    partial = _mk_hwmon(str(tmp_path), idx=0, include_fast=False, slow=11)
    complete = _mk_hwmon(str(tmp_path), idx=7, slow=14, fast=16)

    backend = _backend(tmp_path)

    assert backend.ppt_capability()["supported"] is True
    assert backend.capture_ppt() == {"slow": 14, "fast": 16}
    assert open(os.path.join(partial, "power1_cap")).read().strip() == "11000000"
    assert open(os.path.join(complete, "power1_cap")).read().strip() == "14000000"


def test_legacy_steamdeck_hwmon_keeps_base_control_without_advanced_ppt(tmp_path):
    cap = os.path.join(
        _mk_hwmon(str(tmp_path), name="steamdeck_hwmon", include_fast=False),
        "power1_cap",
    )
    backend = _backend(tmp_path)

    assert backend.supported is True
    assert backend.ppt_capability()["supported"] is False
    assert backend.set_tdp(12, ac=False).ok is True
    assert open(cap).read().strip() == "12000000"


def test_non_deck_surface_is_unsupported(tmp_path):
    _mk_hwmon(str(tmp_path), name="amdgpu")

    other = tmp_path / "other"
    _mk_hwmon(str(other), name="amdgpu")
    assert _backend(other, "rog_ally_x").supported is False


def test_contradictory_labels_disable_advanced_but_not_base(tmp_path):
    _mk_hwmon(str(tmp_path), slow_label="fastPPT", fast_label="slowPPT", maxima=True)
    backend = _backend(tmp_path)

    assert backend.supported is True
    assert backend.ppt_capability()["supported"] is False
    assert backend.diagnostics()["ppt_reason"] == "contradictory_labels"


def test_observe_reports_only_physical_slow_and_fast_rails(tmp_path):
    _mk_hwmon(str(tmp_path), slow=12, fast=15)
    observation = _backend(tmp_path).observe()

    rails = observation.surfaces["steamdeck-hwmon"]
    assert set(rails) == {"pl2", "pl3"}
    assert rails["pl2"].applied_w == 12
    assert rails["pl3"].applied_w == 15


def test_deck_physical_contract_flattens_both_ppt_rails_in_stable_mode(tmp_path):
    _mk_hwmon(str(tmp_path))
    backend = _backend(tmp_path)

    assert backend.primary_rail == "pl2"
    assert backend.physical_levels({
        "pl1": 15, "pl2": 15, "pl3": 15, "mode": "estable",
    }) == {"pl2": 15, "pl3": 15}
    assert backend.physical_levels({
        "pl1": 15, "pl2": 29, "pl3": 30, "mode": "custom",
    }) == {"pl2": 29, "pl3": 30}


def test_raising_ppt_writes_fast_before_slow(tmp_path, monkeypatch):
    _mk_hwmon(str(tmp_path), slow=15, fast=15)
    backend = _backend(tmp_path)
    writes = []
    real_write = deck_module.write_str

    def recording_write(path, value):
        writes.append((os.path.basename(path), int(value)))
        return real_write(path, value)

    monkeypatch.setattr(deck_module, "write_str", recording_write)
    result = backend.apply_ppt(29, 30)

    assert result.ok is True
    assert writes[:2] == [("power2_cap", 30_000_000), ("power1_cap", 29_000_000)]
    assert result.applied == {"slow": 29, "fast": 30}


def test_lowering_ppt_writes_slow_before_fast(tmp_path, monkeypatch):
    _mk_hwmon(str(tmp_path), slow=29, fast=30)
    backend = _backend(tmp_path)
    writes = []
    real_write = deck_module.write_str

    def recording_write(path, value):
        writes.append((os.path.basename(path), int(value)))
        return real_write(path, value)

    monkeypatch.setattr(deck_module, "write_str", recording_write)
    assert backend.apply_ppt(15, 15).ok is True
    assert writes[:2] == [("power1_cap", 15_000_000), ("power2_cap", 15_000_000)]


def test_invalid_order_is_rejected_without_writes(tmp_path, monkeypatch):
    _mk_hwmon(str(tmp_path))
    writes = []
    monkeypatch.setattr(deck_module, "write_str", lambda path, value: writes.append((path, value)))

    result = _backend(tmp_path).apply_ppt(30, 29)

    assert result.ok is False
    assert result.reason == "invalid_order"
    assert writes == []


def test_second_write_failure_rolls_back_both_caps(tmp_path, monkeypatch):
    directory = _mk_hwmon(str(tmp_path), slow=15, fast=15)
    backend = _backend(tmp_path)
    real_write = deck_module.write_str

    def fail_slow(path, value):
        if path.endswith("power1_cap") and int(value) == 29_000_000:
            return False
        return real_write(path, value)

    monkeypatch.setattr(deck_module, "write_str", fail_slow)
    result = backend.apply_ppt(29, 30)

    assert result.ok is False
    assert result.reason == "write_slow"
    assert result.rollback == {"attempted": True, "ok": True}
    assert open(os.path.join(directory, "power1_cap")).read().strip() == "15000000"
    assert open(os.path.join(directory, "power2_cap")).read().strip() == "15000000"


def test_capture_and_restore_rediscover_after_hwmon_renumber(tmp_path):
    directory = _mk_hwmon(str(tmp_path), idx=7, slow=14, fast=16)
    backend = _backend(tmp_path)
    snapshot = backend.capture_ppt()
    assert backend.apply_ppt(29, 30).ok is True
    moved = os.path.join(os.path.dirname(directory), "hwmon2")
    os.rename(directory, moved)

    restored = backend.restore_ppt(snapshot)

    assert restored.ok is True
    assert open(os.path.join(moved, "power1_cap")).read().strip() == "14000000"
    assert open(os.path.join(moved, "power2_cap")).read().strip() == "16000000"


def test_sysfs_bounds_are_intersected_with_the_known_safe_envelope(tmp_path):
    directory = _mk_hwmon(str(tmp_path), maxima=True)
    _write(os.path.join(directory, "power1_cap_min"), 1_000_000)
    _write(os.path.join(directory, "power1_cap_max"), 150_000_000)
    _write(os.path.join(directory, "power2_cap_min"), 1_000_000)
    _write(os.path.join(directory, "power2_cap_max"), 150_000_000)
    backend = _backend(tmp_path)

    capability = backend.ppt_capability()
    rejected = backend.apply_ppt(100, 100)

    assert capability["slow"] == {"min": 3, "max": 29}
    assert capability["fast"] == {"min": 3, "max": 30}
    assert rejected.ok is False
    assert rejected.reason == "invalid_range"


def test_restore_accepts_zero_snapshot_after_capability_metadata_disappears(tmp_path):
    directory = _mk_hwmon(str(tmp_path), slow=0, fast=0, maxima=True)
    backend = _backend(tmp_path)
    snapshot = backend.capture_ppt()
    assert backend.apply_ppt(29, 30).ok is True
    for name in (
        "power1_label", "power2_label", "power1_cap_min", "power1_cap_max",
        "power2_cap_min", "power2_cap_max",
    ):
        os.unlink(os.path.join(directory, name))

    restored = backend.restore_ppt(snapshot)

    assert restored.ok is True
    assert open(os.path.join(directory, "power1_cap")).read().strip() == "0"
    assert open(os.path.join(directory, "power2_cap")).read().strip() == "0"
