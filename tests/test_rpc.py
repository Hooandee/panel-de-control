import asyncio
import importlib
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def Plugin(tmp_path, monkeypatch):
    """Pattern for unit-testing RPC methods off-device. main.py imports `decky` at
    top level and reads decky.DECKY_PLUGIN_SETTINGS_DIR, so inject a fake `decky`
    module pointing settings at a tmp dir BEFORE importing main. Async methods are
    driven with asyncio.run() (no pytest-asyncio needed)."""
    fake = types.ModuleType("decky")
    fake.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake.DECKY_USER = "deck"
    fake.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    monkeypatch.setitem(sys.modules, "decky", fake)
    monkeypatch.syspath_prepend(str(ROOT))
    main = importlib.reload(importlib.import_module("main"))
    return main.Plugin


def test_get_version_returns_package_version(Plugin):
    import json
    pkg = json.loads((ROOT / "package.json").read_text())
    p = Plugin()
    assert asyncio.run(p.get_version()) == pkg["version"]


def test_get_device_returns_detected_profile(Plugin, monkeypatch):
    import device_registry
    from device_profiles import DEVICE_TABLE
    ally_x = next(p for p in DEVICE_TABLE if p.key == "rog_ally_x")
    monkeypatch.setattr(device_registry, "detect", lambda product_name=None: ally_x)
    p = Plugin()
    dev = asyncio.run(p.get_device())
    assert dev["key"] == "rog_ally_x"
    assert dev["display_name"] == "ROG Ally X"
    assert dev["chip"] == "AMD Z1 Extreme"
    assert dev["vendor"] == "amd"
    assert dev["tdp_max"] == 25
    assert dev["tdp_max_charger"] == 30
    assert dev["is_generic"] is False


def test_telemetry_enabled_default_true(Plugin):
    p = Plugin()
    assert asyncio.run(p.get_telemetry_enabled()) is True


def test_set_telemetry_enabled_persists(Plugin):
    p = Plugin()
    assert asyncio.run(p.set_telemetry_enabled(False)) is False
    assert asyncio.run(p.get_telemetry_enabled()) is False
    # Persisted across a fresh Plugin instance (same settings dir).
    p2 = Plugin()
    assert asyncio.run(p2.get_telemetry_enabled()) is False
    asyncio.run(p2.set_telemetry_enabled(True))
    assert asyncio.run(Plugin().get_telemetry_enabled()) is True
