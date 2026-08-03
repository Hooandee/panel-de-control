import sys
import types


if "decky" not in sys.modules:
    decky = types.ModuleType("decky")
    decky.DECKY_PLUGIN_SETTINGS_DIR = "/tmp"
    decky.DECKY_USER = "deck"
    decky.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    sys.modules["decky"] = decky

import main


class _Store:
    def __init__(self):
        self.saves = 0

    def save(self, settings):
        self.saves += 1


class _Result:
    def __init__(self, ok, reason=None):
        self.ok = ok
        self.reason = reason


class _DeckBackend:
    name = "steamdeck-hwmon"

    def __init__(self, restore_ok=True):
        self.restore_ok = restore_ok
        self.capture_calls = 0
        self.restore_calls = []
        self.snapshot = {"slow": 14, "fast": 16}

    def ppt_capability(self):
        return {"supported": True}

    def capture_ppt(self):
        self.capture_calls += 1
        return dict(self.snapshot)

    def restore_ppt(self, snapshot):
        self.restore_calls.append(dict(snapshot))
        return _Result(self.restore_ok, None if self.restore_ok else "write_fast")


def _plugin(backend):
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._tdp_backend = backend
    plugin._settings = {"steamdeck_ppt_previous": None}
    plugin._store = _Store()
    plugin._tdp_history = []
    return plugin


def _command(mode):
    return types.SimpleNamespace(
        logical_requested={"pl1": 15, "pl2": 29, "pl3": 30, "mode": mode},
        requested={"pl2": 29, "pl3": 30} if mode != "estable" else {"pl2": 15},
    )


def test_first_advanced_apply_persists_snapshot_before_takeover():
    backend = _DeckBackend()
    plugin = _plugin(backend)

    assert plugin._prepare_steamdeck_ppt(_command("custom")) is None

    assert plugin._settings["steamdeck_ppt_previous"] == {"slow": 14, "fast": 16}
    assert backend.capture_calls == 1
    assert plugin._store.saves == 1


def test_later_advanced_apply_does_not_replace_original_snapshot():
    backend = _DeckBackend()
    plugin = _plugin(backend)
    plugin._settings["steamdeck_ppt_previous"] = {"slow": 13, "fast": 15}

    assert plugin._prepare_steamdeck_ppt(_command("auto")) is None

    assert backend.capture_calls == 0
    assert plugin._settings["steamdeck_ppt_previous"] == {"slow": 13, "fast": 15}


def test_stable_restores_and_only_then_clears_marker():
    backend = _DeckBackend()
    plugin = _plugin(backend)
    plugin._settings["steamdeck_ppt_previous"] = {"slow": 13, "fast": 15}

    assert plugin._prepare_steamdeck_ppt(_command("estable")) is None

    assert backend.restore_calls == [{"slow": 13, "fast": 15}]
    assert plugin._settings["steamdeck_ppt_previous"] is None


def test_failed_release_keeps_marker_and_blocks_handoff():
    backend = _DeckBackend(restore_ok=False)
    plugin = _plugin(backend)
    marker = {"slow": 13, "fast": 15}
    plugin._settings["steamdeck_ppt_previous"] = marker

    failure = plugin._prepare_steamdeck_ppt(_command("estable"))

    assert failure == "write_fast"
    assert plugin._settings["steamdeck_ppt_previous"] == marker
    assert plugin._restore_steamdeck_ppt() is False
