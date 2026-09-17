import asyncio
import copy
import importlib
import json
import sys
import types

import pytest

from settings_store import SettingsStore


@pytest.fixture
def load_settings_plugin(tmp_path, monkeypatch):
    decky = types.ModuleType("decky")
    decky.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    decky.DECKY_USER = "deck"
    decky.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "decky", decky)
    main = importlib.reload(importlib.import_module("main"))

    def load():
        plugin = main.Plugin()
        plugin._store = SettingsStore(str(tmp_path / "state.json"))
        plugin._settings = plugin._store.load(main.DEFAULTS)
        # Exercise persistence and the real UI RPC without starting hardware owners.
        plugin._ready = True
        return plugin

    return load


@pytest.mark.parametrize("restore_pending", [False, True])
def test_ui_save_after_upgrade_preserves_active_settings(
    tmp_path, load_settings_plugin, restore_pending
):
    settings = {
        "low_battery_tdp_hold": True,
        "charge_limit_enabled": True,
        "charge_limit_percent": 85,
        "charge_limit_full_once_until": 4_000_000_000.25,
        "charge_limit_full_once_restore_pending": restore_pending,
        "cpu_frequency_handoff": {
            "version": 1,
            "boot_id": "upgrade-fixture-boot",
            "requested": [1_200_000, 2_400_000],
            "baseline": [{
                "identity": [
                    "policy0", "/sys/devices/system/cpu/cpufreq/policy0",
                    "amd-pstate-epp", [0, 1], 400_000, 5_100_000,
                ],
                "window": [400_000, 5_100_000],
            }],
        },
        "steamdeck_ppt_previous": {"slow": 25, "fast": 30},
        "telemetry_enabled": False,
        "qam_tdp_boost": True,
        "disabled_modules": ["audio"],
        "ui_prefs": {
            "panel-de-control-lang": "es",
            "pdc:valueToast:enabled": "1",
            "pdc:qamShortcut": "1",
        },
    }
    path = tmp_path / "state.json"
    path.write_text(json.dumps(settings))
    plugin = load_settings_plugin()
    qam_layout = json.dumps({
        "order": ["pdc:home", "native:4", "decky"],
        "hiddenNative": [],
        "pinnedViews": ["pdc:home"],
        "ownedIds": {"pdc:home": 5260355},
    })

    assert asyncio.run(plugin.set_ui_prefs({"pdc:qamLayout": qam_layout})) is True

    expected = copy.deepcopy(settings)
    expected["ui_prefs"]["pdc:qamLayout"] = qam_layout
    saved = json.loads(path.read_text())
    assert {key: saved[key] for key in expected} == expected
    reloaded = load_settings_plugin()
    assert {key: reloaded._settings[key] for key in expected} == expected
    assert asyncio.run(reloaded.get_ui_prefs()) == expected["ui_prefs"]
