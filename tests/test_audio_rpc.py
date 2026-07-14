"""RPC-level tests for the Sonido (audio EQ) controls. Same Plugin bootstrap as the
other RPC tests: fake decky + fake TDP backend so _init never touches hardware, plus a
fake PipeWireEq so no real audio stack is needed and we can assert what got applied."""
import asyncio
import importlib
import sys
import types


class _FakePipeWireEq:
    def __init__(self, supported=True, route="speaker"):
        self._supported = supported
        self._route = route
        self.applied = []
        self.torn_down = 0

    def is_supported(self):
        return self._supported

    def current_route(self):
        return self._route

    def set_gains(self, gains, preamp):
        self.applied.append((list(gains), preamp))
        return True

    def teardown(self):
        self.torn_down += 1


def _make_plugin(tmp_path, monkeypatch, audio=None):
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
        supports_levels = False
        name = "fake"

        def get_limits(self):
            return TdpLimits(min_w=5, default_w=15, max_w=20, max_ac_w=60)

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
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)

    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)

    fake_audio = audio if audio is not None else _FakePipeWireEq()
    monkeypatch.setattr(main, "PipeWireEq", lambda *a, **k: fake_audio)
    return main.Plugin(), fake_audio


def test_default_disabled_but_supported(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.get_audio_state())
    assert st["supported"] is True
    assert st["enabled"] is False
    assert st["gains"] == [0.0] * 10
    assert st["route"] == "speaker"


def test_enable_applies(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_audio_enabled(True))
    assert st["enabled"] is True
    assert fake.applied  # set_gains was called


def test_disable_tears_down(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_audio_enabled(True))
    st = asyncio.run(p.set_audio_enabled(False))
    assert st["enabled"] is False
    assert fake.torn_down >= 1


def test_apply_preset_persists(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.apply_audio_preset("bass", "global"))
    assert st["preset"] == "bass"
    assert any(g != 0.0 for g in st["gains"])


def test_set_band_marks_custom(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_audio_band(0, 6.0, "global"))
    assert st["gains"][0] == 6.0
    assert st["preset"] == "custom"
    assert st["preamp"] == -6.0


def test_set_bands_replaces_all(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_audio_bands([2] * 10, "global"))
    assert st["gains"] == [2.0] * 10
    assert st["preset"] == "custom"


def test_reset_flattens(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_audio_band(3, 9.0, "global"))
    st = asyncio.run(p.reset_audio("global"))
    assert st["gains"] == [0.0] * 10


def test_game_scope_independent_of_global(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_audio_band(0, 2.0, "global"))
    asyncio.run(p.set_audio_band(0, 8.0, "game", appid="42"))
    # game keeps its own; toggling follow-global reverts to the global value
    st_game = asyncio.run(p.get_audio_state())
    assert st_game["gains"][0] == 8.0
    st_follow = asyncio.run(p.set_audio_follow_global(True, "42"))
    assert st_follow["gains"][0] == 2.0


def test_unsupported_hides_controls(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch, audio=_FakePipeWireEq(supported=False))
    st = asyncio.run(p.get_audio_state())
    assert st["supported"] is False
