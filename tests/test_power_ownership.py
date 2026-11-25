import json

import pytest

from power_ownership import OwnershipConflict, PowerOwnershipStore


def test_absent_observation_preserves_legacy_and_unknown_blocks(tmp_path):
    store = PowerOwnershipStore(tmp_path / "owners.json")
    state = store.set_context("42")
    assert state["observed"] is False
    assert state["steam_profile"] is None
    assert state["owner"] == "pdc"
    assert state["write_allowed"] is True
    state = store.observe("42", "unknown")
    assert state["observed"] is True
    assert state["owner"] == "unresolved"
    assert state["write_allowed"] is False


@pytest.mark.parametrize("profile,owner,allowed", [
    ("active", "steam", False),
    ("inactive", "pdc", True),
    ("unknown", "unresolved", False),
])
def test_observed_steam_profile_selects_default(tmp_path, profile, owner, allowed):
    state = PowerOwnershipStore(tmp_path / "owners.json").observe("42", profile)
    assert state["owner"] == owner
    assert state["explicit_owner"] is None
    assert state["write_allowed"] is allowed


def test_choice_survives_restart_and_does_not_follow_other_game(tmp_path):
    path = tmp_path / "owners.json"
    store = PowerOwnershipStore(path)
    observed = store.observe("42", "active")
    claimed = store.set_owner("42", "pdc", observed["revision"])
    assert claimed["explicit_owner"] == "pdc"
    assert claimed["write_allowed"] is True
    reloaded = PowerOwnershipStore(path)
    assert reloaded.observe("42", "active")["owner"] == "pdc"
    assert reloaded.observe("43", "active")["owner"] == "steam"
    state = reloaded.observe("42", "unknown")
    released = reloaded.set_owner("42", "steam", state["revision"])
    assert released["write_allowed"] is False
    assert PowerOwnershipStore(path).observe("42", "inactive")["owner"] == "steam"


def test_changed_context_or_observation_rejects_old_confirmation(tmp_path):
    store = PowerOwnershipStore(tmp_path / "owners.json")
    old = store.observe("42", "active")
    current = store.observe("42", "inactive")
    with pytest.raises(OwnershipConflict, match="stale_revision"):
        store.set_owner("42", "pdc", old["revision"])
    assert store.state() == current
    current = store.observe("43", "active")
    with pytest.raises(OwnershipConflict, match="stale_context"):
        store.set_owner("42", "pdc", current["revision"])
    assert store.state() == current


def test_repeated_observation_keeps_confirmation_valid_but_owner_change_invalidates(tmp_path):
    store = PowerOwnershipStore(tmp_path / "owners.json")
    state = store.observe("42", "active")
    assert store.observe("42", "active") == state
    claimed = store.set_owner("42", "pdc", state["revision"])
    with pytest.raises(OwnershipConflict, match="stale_revision"):
        store.set_owner("42", "steam", state["revision"])
    assert store.state() == claimed


def test_context_change_clears_observation_without_leaking_owner(tmp_path):
    store = PowerOwnershipStore(tmp_path / "owners.json")
    old = store.observe("42", "active")
    current = store.set_context("43")
    assert current["observed"] is False
    assert current["steam_profile"] is None
    assert current["revision"] != old["revision"]
    assert store.set_context("43") == current
    assert store.set_context(None)["context_appid"] is None


def test_failed_atomic_replace_preserves_memory_and_previous_file(tmp_path, monkeypatch):
    import json_store

    path = tmp_path / "owners.json"
    store = PowerOwnershipStore(path)
    state = store.observe("42", "active")
    state = store.set_owner("42", "pdc", state["revision"])
    previous = path.read_bytes()

    def fail_replace(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(json_store.os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk failure"):
        store.set_owner("42", "steam", state["revision"])
    assert store.state() == state
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("raw", [None, [], {"games": []}, {"games": {"42": "bad"}}])
def test_corrupt_store_cannot_grant_explicit_ownership(tmp_path, raw):
    path = tmp_path / "owners.json"
    path.write_text(json.dumps(raw))
    state = PowerOwnershipStore(path).observe("42", "active")
    assert state["explicit_owner"] is None
    assert state["owner"] == "steam"


def test_invalid_inputs_leave_context_and_file_unchanged(tmp_path):
    path = tmp_path / "owners.json"
    store = PowerOwnershipStore(path)
    state = store.observe("42", "active")
    for profile in (None, True, "bad", {}):
        with pytest.raises(ValueError):
            store.observe("43", profile)
        assert store.state() == state
    for owner in (None, "bad", {}):
        with pytest.raises(ValueError):
            store.set_owner("42", owner, state["revision"])
    with pytest.raises(OwnershipConflict):
        store.set_owner("42", "pdc", True)
    with pytest.raises(ValueError):
        store.set_owner(None, "pdc", state["revision"])
    assert store.state() == state
    assert not path.exists()


def test_settings_claim_is_atomic_survives_reload_and_preserves_other_games(tmp_path):
    path = tmp_path / "owners.json"
    path.write_text(json.dumps({"version": 1, "games": {"43": {"owner": "steam"}}}))
    store = PowerOwnershipStore(path)
    state = store.observe("42", "active")
    snapshot = {"vrr": True, "refreshRate": 60, "sharpness": 2.5}
    claimed = store.set_owner("42", "pdc", state["revision"], snapshot)
    snapshot["refreshRate"] = 90
    assert claimed["steam_settings"]["refreshRate"] == 60
    claimed["steam_settings"]["refreshRate"] = 120
    assert store.state()["steam_settings"]["refreshRate"] == 60
    reloaded = PowerOwnershipStore(path)
    state = reloaded.observe("42", "active")
    assert state["owner"] == "pdc"
    assert state["steam_settings"] == {"vrr": True, "refreshRate": 60, "sharpness": 2.5}
    released = reloaded.set_owner("42", "steam", state["revision"])
    assert released["write_allowed"] is False
    assert released["steam_settings"] == state["steam_settings"]
    assert reloaded.observe("43", "active")["explicit_owner"] == "steam"
    assert reloaded.state()["steam_settings"] == {}
    assert PowerOwnershipStore(path).observe("42", "active")["steam_settings"] == state["steam_settings"]


@pytest.mark.parametrize("snapshot", [[], {"reset": 1}, {"unknown": 0}, {"vrr": 1}, {"refreshRate": True}, {"sharpness": -1}, {"sharpness": float("nan")}, {"refreshRate": float("inf")}, {str(i): i for i in range(21)}])
def test_invalid_settings_cannot_claim_or_change_state(tmp_path, snapshot):
    path = tmp_path / "owners.json"
    store = PowerOwnershipStore(path)
    before = store.observe("42", "active")
    with pytest.raises(ValueError, match="invalid_steam_settings"):
        store.set_owner("42", "pdc", before["revision"], snapshot)
    assert store.state() == before
    assert not path.exists()


def test_setting_requires_explicit_owner_context_and_revision(tmp_path):
    store = PowerOwnershipStore(tmp_path / "owners.json")
    state = store.observe("42", "inactive")
    with pytest.raises(OwnershipConflict, match="pdc_owner_required"):
        store.set_steam_setting("42", state["revision"], "vrr", True)
    state = store.set_owner("42", "pdc", state["revision"], {"refreshRate": 60})
    with pytest.raises(OwnershipConflict, match="stale_context"):
        store.set_steam_setting("43", state["revision"], "vrr", True)
    with pytest.raises(OwnershipConflict, match="stale_revision"):
        store.set_steam_setting("42", state["revision"] - 1, "vrr", True)
    with pytest.raises(ValueError):
        store.set_steam_setting("42", state["revision"], "reset", 1)
    assert store.state() == state
    updated = store.set_steam_setting("42", state["revision"], "vrr", True)
    assert updated["revision"] == state["revision"] + 1
    assert updated["steam_settings"] == {"refreshRate": 60, "vrr": True}
    reloaded = PowerOwnershipStore(tmp_path / "owners.json")
    assert reloaded.observe("42", "active")["steam_settings"] == updated["steam_settings"]
    released = store.set_owner("42", "steam", updated["revision"])
    with pytest.raises(OwnershipConflict, match="pdc_owner_required"):
        store.set_steam_setting("42", released["revision"], "vrr", False)


@pytest.mark.parametrize("operation", ["claim", "setting"])
def test_settings_persistence_failure_preserves_owner_revision_and_file(tmp_path, monkeypatch, operation):
    import json_store

    path = tmp_path / "owners.json"
    store = PowerOwnershipStore(path)
    state = store.observe("42", "active")
    state = store.set_owner("42", "pdc" if operation == "setting" else "steam", state["revision"], {"vrr": False})
    original = path.read_bytes()

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(json_store.os, "replace", fail)
    with pytest.raises(OSError, match="disk failure"):
        if operation == "claim":
            store.set_owner("42", "pdc", state["revision"], {"vrr": True})
        else:
            store.set_steam_setting("42", state["revision"], "vrr", True)
    assert store.state() == state
    assert path.read_bytes() == original


def test_invalid_saved_settings_do_not_discard_valid_owner(tmp_path):
    path = tmp_path / "owners.json"
    path.write_text(json.dumps({"games": {"42": {"owner": "pdc", "steam_settings": {"reset": 1}}}}))
    state = PowerOwnershipStore(path).observe("42", "active")
    assert state["owner"] == "pdc"
    assert state["steam_settings"] == {}


def test_same_owner_snapshot_update_persists_reset_without_losing_other_games(tmp_path):
    path = tmp_path / "owners.json"
    store = PowerOwnershipStore(path)
    state = store.observe("42", "active")
    state = store.set_owner("42", "pdc", state["revision"], {"vrr": True})
    reset = store.set_owner("42", "pdc", state["revision"], {"vrr": False})
    assert reset["revision"] == state["revision"] + 1
    assert PowerOwnershipStore(path).observe("42", "active")["steam_settings"] == {"vrr": False}
    assert store.set_owner("42", "pdc", reset["revision"], {"vrr": False}) == reset


def test_legacy_scaling_settings_survive_claim_and_reload(tmp_path):
    path = tmp_path / 'ownership.json'
    store = PowerOwnershipStore(path)
    state = store.observe('42', 'active')
    values = {'combinedScaling': 5, 'fsrSharpness': 2, 'nisSharpness': 3}
    store.set_owner('42', 'pdc', state['revision'], values)
    assert PowerOwnershipStore(path).observe('42', 'active')['steam_settings'] == values
