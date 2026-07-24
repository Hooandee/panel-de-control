import json

import power_presets
import pytest
from power_presets import BUILTIN_IDS, PowerPresetStore

_ESTABLE = {"mode": "estable", "off2": 0, "off3": 0}


def _store(tmp_path):
    return PowerPresetStore(str(tmp_path / "power_presets.json"))


def test_fresh_state_lists_builtins_in_default_order(tmp_path):
    s = _store(tmp_path)
    st = s.state()
    assert st["order"] == list(BUILTIN_IDS)
    assert st["hidden"] == []
    assert st["custom"] == {}


def test_create_appends_custom_with_sequential_id(tmp_path):
    s = _store(tmp_path)
    st = s.create(12, "bolt", None)
    assert st["order"][-1] == "c1"
    assert st["custom"]["c1"] == {"watts": 12, "icon": "bolt", "name": "", "boost": _ESTABLE}
    st2 = s.create(8, "leaf", None)
    assert st2["order"][-1] == "c2"  # never reuses ids


def test_create_and_update_store_a_name(tmp_path):
    s = _store(tmp_path)
    st = s.create(12, "bolt", None, name="  Streaming  ")
    assert st["custom"]["c1"]["name"] == "Streaming"  # trimmed
    st = s.update("c1", 12, "bolt", None, name="Emu")
    assert st["custom"]["c1"]["name"] == "Emu"
    # persists
    assert PowerPresetStore(str(tmp_path / "power_presets.json")).state()["custom"]["c1"]["name"] == "Emu"


def test_create_clamps_and_coerces_boost(tmp_path):
    s = _store(tmp_path)
    st = s.create(999, "x", {"mode": "custom", "off2": -5, "off3": 3}, min_w=5, max_w=30)
    c = st["custom"]["c1"]
    assert c["watts"] == 30  # clamped to max
    assert c["boost"] == {"mode": "custom", "off2": 0, "off3": 3}  # off2 floored at 0


def test_update_only_custom(tmp_path):
    s = _store(tmp_path)
    s.create(12, "bolt", None)
    st = s.update("c1", 15, "leaf", None)
    assert st["custom"]["c1"] == {"watts": 15, "icon": "leaf", "name": "", "boost": _ESTABLE}
    # updating a builtin id is a no-op (not editable)
    before = s.state()
    assert s.update("quiet", 5, "x", None) == before


def test_delete_only_custom_removes_from_order_and_hidden(tmp_path):
    s = _store(tmp_path)
    s.create(12, "bolt", None)
    s.set_hidden("c1", True)
    st = s.delete("c1")
    assert "c1" not in st["custom"]
    assert "c1" not in st["order"]
    assert "c1" not in st["hidden"]
    # deleting a builtin is a no-op
    assert "quiet" in s.delete("quiet")["order"]


def test_move_reorders_any_id(tmp_path):
    s = _store(tmp_path)
    st = s.move("quiet", 1)  # quiet down one
    assert st["order"][:2] == ["balanced", "quiet"]
    st = s.move("quiet", -1)  # back up
    assert st["order"][:2] == ["quiet", "balanced"]
    # edge no-op: quiet at index 0 can't move up
    assert s.move("quiet", -1)["order"] == st["order"]


def test_set_hidden_toggles_membership(tmp_path):
    s = _store(tmp_path)
    assert "turbo" in s.set_hidden("turbo", True)["hidden"]
    assert "turbo" not in s.set_hidden("turbo", False)["hidden"]


def test_persists_across_instances(tmp_path):
    p = tmp_path / "power_presets.json"
    s = PowerPresetStore(str(p))
    s.create(12, "bolt", None)
    s.set_hidden("quiet", True)
    s2 = PowerPresetStore(str(p))
    assert s2.state()["custom"]["c1"]["watts"] == 12
    assert "quiet" in s2.state()["hidden"]


def test_coerce_survives_non_finite_watts(tmp_path):
    # JSON `1e309` parses to float('inf'); int(inf) raises OverflowError. Must not brick.
    p = tmp_path / "power_presets.json"
    p.write_text('{"custom":{"c1":{"watts":1e309}}}')
    s = PowerPresetStore(str(p))
    assert s.state()["custom"]["c1"]["watts"] == 10  # fell back to the default


def test_save_failure_reverts_and_raises(tmp_path, monkeypatch):
    s = _store(tmp_path)

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(power_presets, "atomic_json_save", boom)
    with pytest.raises(OSError):
        s.create(12, "bolt", None)
    # In-memory reverted to disk (last good) — no fake preset lingers.
    assert s.state()["custom"] == {}


def test_load_caps_custom_at_max(tmp_path):
    # A stale/hand-edited file with thousands of presets must not load them all — the
    # frontend would build thousands of focusable rows and freeze the QAM.
    from power_presets import _MAX_CUSTOM
    p = tmp_path / "power_presets.json"
    n = _MAX_CUSTOM + 50
    customs = {f"c{i}": {"watts": 10, "icon": "bolt"} for i in range(1, n + 1)}
    p.write_text(json.dumps({"custom": customs, "order": list(customs), "seq": n}))
    st = PowerPresetStore(str(p)).state()
    assert len(st["custom"]) == _MAX_CUSTOM
    assert len([i for i in st["order"] if i.startswith("c")]) == _MAX_CUSTOM
    assert set(BUILTIN_IDS).issubset(set(st["order"]))
    # keeps the first N by order
    assert st["order"][:1] == ["c1"] or "c1" in st["custom"]


def test_coerce_survives_garbage_and_phantom_ids(tmp_path):
    p = tmp_path / "power_presets.json"
    p.write_text(json.dumps({
        "order": ["ghost", "turbo", 5, "quiet"],
        "hidden": ["ghost", "balanced"],
        "custom": {"c9": {"watts": "bad", "icon": 3}},
        "seq": "nope",
    }))
    s = PowerPresetStore(str(p))
    st = s.state()
    assert set(st["order"]) == set(BUILTIN_IDS) | {"c9"}
    assert "ghost" not in st["hidden"]
    assert st["custom"]["c9"]["watts"] >= 1
    assert isinstance(st["custom"]["c9"]["icon"], str)
    # next create continues past the highest existing id
    assert s.create(10, "x", None)["order"][-1] == "c10"
