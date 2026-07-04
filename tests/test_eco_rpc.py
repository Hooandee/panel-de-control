"""RPC-level tests for download mode (eco): override + restore + manual clear."""
import asyncio
import importlib
import sys
import types


class _FakeToggle:
    def __init__(self, supported=True, on=True):
        self.supported = supported
        self._on = on

    def enabled(self):
        return self._on if self.supported else False

    def set(self, enabled):
        if not self.supported:
            return False
        self._on = bool(enabled)
        return True


def _make_plugin(tmp_path, monkeypatch, boost=None):
    fake_decky = types.ModuleType("decky")
    fake_decky.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake_decky.DECKY_USER = "deck"
    fake_decky.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    monkeypatch.setitem(sys.modules, "decky", fake_decky)

    import tdp.factory as factory
    from tdp.types import TdpLimits, TdpResult

    class _FakeBackend:
        supported = True
        supports_levels = True
        name = "fake"

        def get_limits(self):
            return TdpLimits(min_w=5, default_w=15, max_w=20, max_ac_w=20)

        def level_limits(self):
            return {}

        def set_tdp(self, w, ac):
            return TdpResult(w, w, True, "")

        def set_levels(self, pl1, pl2, pl3, ac):
            return TdpResult(pl1, pl1, True, "")

        def read_applied(self):
            return 15

    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: _FakeBackend())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": False)
    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": False, raising=False)

    if boost is not None:
        original_init = main.Plugin._init

        def patched_init(self):
            original_init(self)
            self._boost = boost

        monkeypatch.setattr(main.Plugin, "_init", patched_init)

    return main.Plugin()


def test_get_eco_state_shape(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, boost=_FakeToggle())
    st = asyncio.run(p.get_eco_state())
    assert st["enabled"] is False
    assert st["tdp_min_w"] == 5
    assert st["affects_boost"] is True


def test_eco_on_forces_min_tdp_and_boost_off(tmp_path, monkeypatch):
    boost = _FakeToggle(on=True)
    p = _make_plugin(tmp_path, monkeypatch, boost=boost)
    st = asyncio.run(p.set_eco(True, 55))
    assert st["enabled"] is True
    assert st["wake_brightness"] == 55  # snapshot of the passed brightness
    # effective TDP forced to the device minimum, overriding any profile
    levels, _active, _ac = p._effective_levels(None)
    assert levels["pl1"] == 5 and levels["pl2"] == 5 and levels["pl3"] == 5
    assert boost.enabled() is False  # boost forced off


def test_eco_off_restores(tmp_path, monkeypatch):
    boost = _FakeToggle(on=True)
    p = _make_plugin(tmp_path, monkeypatch, boost=boost)
    p._init()
    before = p._effective_levels(None)[0]["pl1"]  # normal setpoint before eco
    asyncio.run(p.set_eco(True, 55))
    assert p._effective_levels(None)[0]["pl1"] == 5  # forced to min while on
    st = asyncio.run(p.set_eco(False, 0))
    assert st["enabled"] is False
    assert p._effective_levels(None)[0]["pl1"] == before  # restored, not stuck at min
    assert boost.enabled() is True  # boost restored to saved setting


def test_manual_tdp_change_clears_eco(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, boost=_FakeToggle())
    asyncio.run(p.set_eco(True, 40))
    assert p._settings["eco_enabled"] is True
    asyncio.run(p.set_tdp_watts(18, "global", None))
    assert p._settings["eco_enabled"] is False  # manual control exits eco


def test_zero_brightness_snapshot_is_ignored(tmp_path, monkeypatch):
    # FE may pass 0 while brightness is still loading; storing it would restore the
    # screen to black on exit. The snapshot must keep the previous (default) value.
    p = _make_plugin(tmp_path, monkeypatch, boost=_FakeToggle())
    st = asyncio.run(p.set_eco(True, 0))
    assert st["wake_brightness"] == 40  # default kept, not 0


def test_manual_boost_change_clears_eco(tmp_path, monkeypatch):
    boost = _FakeToggle(on=True)
    p = _make_plugin(tmp_path, monkeypatch, boost=boost)
    asyncio.run(p.set_eco(True, 40))
    asyncio.run(p.set_cpu_boost(True))
    assert p._settings["eco_enabled"] is False
    assert boost.enabled() is True
