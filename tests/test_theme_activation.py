import json

import pytest

import theme_activation


def snapshot(plugin_version="2.1.2", backend_version=9):
    return {
        "status": "ready",
        "pluginVersion": plugin_version,
        "backendVersion": backend_version,
        "themes": [{
            "id": "example",
            "name": "Example Theme",
            "displayName": "Example Theme",
            "version": "1.2.3",
            "author": "Example Author",
            "enabled": False,
            "patches": [{
                "name": "Color",
                "defaultValue": "Blue",
                "value": "Red",
                "options": ["Blue", "Red"],
                "type": "dropdown",
                "rawType": "dropdown",
            }],
        }],
    }


def test_activation_recovery_survives_restart_until_exact_acknowledgement(tmp_path):
    path = tmp_path / "activation.json"

    prepared = theme_activation.begin_theme_activation(snapshot(), path)
    recovery = theme_activation.get_theme_activation_recovery(path)

    assert prepared["code"] == "prepared"
    assert recovery == {
        "transaction": prepared["transaction"],
        "snapshot": snapshot(),
        "recoverable": False,
    }
    theme_activation.mark_theme_activation_settled(prepared["transaction"], path)
    assert theme_activation.get_theme_activation_recovery(path)["recoverable"] is True
    with pytest.raises(theme_activation.ThemeActivationJournalError) as mismatch:
        theme_activation.acknowledge_theme_activation("wrong-token", path)
    assert mismatch.value.code == "invalid_transaction"
    assert path.is_file()

    acknowledged = theme_activation.acknowledge_theme_activation(
        prepared["transaction"],
        path,
    )

    assert acknowledged == {"ok": True, "code": "acknowledged"}
    assert theme_activation.get_theme_activation_recovery(path) is None
    assert path.is_file()
    assert theme_activation.acknowledge_theme_activation(
        prepared["transaction"],
        path,
    ) == {"ok": True, "code": "acknowledged"}
    assert theme_activation.mark_theme_activation_settled(
        prepared["transaction"],
        path,
    ) == {"ok": True, "code": "settled"}


def test_activation_recovery_rejects_overwriting_a_pending_transaction(tmp_path):
    path = tmp_path / "activation.json"
    theme_activation.begin_theme_activation(snapshot(), path)

    with pytest.raises(theme_activation.ThemeActivationJournalError) as pending:
        theme_activation.begin_theme_activation(snapshot(), path)

    assert pending.value.code == "recovery_pending"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(status="missing"),
        lambda value: value.update(backendVersion=True),
        lambda value: value["themes"][0].update(enabled=1),
        lambda value: value["themes"][0]["patches"][0].update(options=["ok", 1]),
        lambda value: value["themes"][0].update(extra="hidden"),
    ],
)
def test_activation_recovery_rejects_malformed_snapshots(tmp_path, mutate):
    value = snapshot()
    mutate(value)

    with pytest.raises(theme_activation.ThemeActivationJournalError) as invalid:
        theme_activation.begin_theme_activation(value, tmp_path / "activation.json")

    assert invalid.value.code == "invalid_snapshot"


def test_activation_recovery_fails_closed_on_corrupt_persistent_state(tmp_path):
    path = tmp_path / "activation.json"
    path.write_text(json.dumps({"schema_version": 1, "transaction": "forged"}))

    with pytest.raises(theme_activation.ThemeActivationJournalError) as corrupt:
        theme_activation.get_theme_activation_recovery(path)

    assert corrupt.value.code == "invalid_journal"


def test_unsettled_recovery_remains_blocked_across_restart(tmp_path):
    path = tmp_path / "activation.json"
    prepared = theme_activation.begin_theme_activation(snapshot(), path)

    assert theme_activation.get_theme_activation_recovery(path)["recoverable"] is False
    assert theme_activation.get_theme_activation_recovery(path) == {
        "transaction": prepared["transaction"],
        "snapshot": snapshot(),
        "recoverable": False,
    }


def test_activation_acknowledgement_is_idempotent_after_ambiguous_commit(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "activation.json"
    prepared = theme_activation.begin_theme_activation(snapshot(), path)
    token = prepared["transaction"]
    theme_activation.mark_theme_activation_settled(token, path)
    original_fsync = theme_activation._fsync_directory
    monkeypatch.setattr(
        theme_activation,
        "_fsync_directory",
        lambda _path: (_ for _ in ()).throw(OSError("response lost after replace")),
    )

    with pytest.raises(OSError):
        theme_activation.acknowledge_theme_activation(token, path)

    monkeypatch.setattr(theme_activation, "_fsync_directory", original_fsync)
    assert theme_activation.get_theme_activation_recovery(path) is None
    assert theme_activation.mark_theme_activation_settled(token, path)["code"] == "settled"
    assert theme_activation.acknowledge_theme_activation(token, path)["code"] == "acknowledged"


def test_activation_journal_never_writes_a_wrapper_larger_than_its_read_limit(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "activation.json"
    encoded_snapshot = json.dumps(snapshot(), separators=(",", ":")).encode("utf-8")
    monkeypatch.setattr(theme_activation, "_MAX_JOURNAL_BYTES", len(encoded_snapshot) + 32)

    with pytest.raises(theme_activation.ThemeActivationJournalError) as too_large:
        theme_activation.begin_theme_activation(snapshot(), path)

    assert too_large.value.code == "invalid_snapshot"
    assert not path.exists()
