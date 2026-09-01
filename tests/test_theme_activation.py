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
    }
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
