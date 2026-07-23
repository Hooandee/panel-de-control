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

    def set_gains(self, gains, bass=0, loudness=False, crossfeed=0, stereo_width=50):
        self.applied.append((list(gains), bass, loudness, crossfeed, stereo_width))
        return True

    def start_test(self, path):
        self._playing = True

    def stop_test(self):
        self._playing = False

    def is_test_playing(self):
        return getattr(self, "_playing", False)

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


def test_set_bands_replaces_all(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_audio_bands([2] * 10, "global"))
    assert st["gains"] == [2.0] * 10
    assert st["preset"] == "custom"


def test_set_curve_sets_gains_and_bass_together(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_audio_curve([3] * 10, 60, "global"))
    assert st["gains"] == [3.0] * 10 and st["bass"] == 60
    # applying an EQ preset must not wipe the bass amount
    st = asyncio.run(p.apply_audio_preset("voices", "global"))
    assert st["bass"] == 60 and st["preset"] == "voices"


def test_save_apply_delete_profile(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_audio_bands([4] * 10, "global"))
    st = asyncio.run(p.save_audio_profile("Peli"))
    assert any(pr["name"] == "Peli" for pr in st["profiles"])
    # change the curve, then re-apply the saved profile → back to [4]*10
    asyncio.run(p.set_audio_bands([0] * 10, "global"))
    st = asyncio.run(p.apply_audio_profile("Peli", "global"))
    assert st["gains"] == [4.0] * 10
    st = asyncio.run(p.delete_audio_profile("Peli"))
    assert st["profiles"] == []


def test_loudness_toggle_and_preserved(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_audio_loudness(True, "global"))
    assert st["loudness"] is True
    st = asyncio.run(p.apply_audio_preset("voices", "global"))  # preset keeps loudness
    assert st["loudness"] is True and st["preset"] == "voices"


def test_toggle_test_tone(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_audio_test(True))
    assert st["test_playing"] is True
    assert st["test_sample"] == "full"
    assert st["test_samples"] == ["bass", "voice", "treble", "full"]
    st = asyncio.run(p.set_audio_test(False))
    assert st["test_playing"] is False
    assert st["test_sample"] is None


def test_test_sample_selection(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.set_audio_test(True, "bass"))
    assert st["test_playing"] is True and st["test_sample"] == "bass"
    # switching focus keeps playing, updates the active sample
    st = asyncio.run(p.set_audio_test(True, "treble"))
    assert st["test_sample"] == "treble"


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


def test_guard_on_by_default_and_exposes_limits(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.get_audio_state())
    assert st["guard"] is True
    assert len(st["safe_limits"]["bands"]) == 10
    assert st["safe_limits"]["bass"] > 0


def test_guard_clamps_applied_boost_but_keeps_stored_curve(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_audio_enabled(True))
    st = asyncio.run(p.set_audio_bands([12] * 10, "global"))
    ceilings = st["safe_limits"]["bands"]
    assert st["gains"] == [12.0] * 10                       # stored/reported curve is raw
    assert fake.applied[-1][0] == [float(c) for c in ceilings]  # applied is clamped


def test_guard_clamps_applied_bass(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_audio_enabled(True))
    st = asyncio.run(p.set_audio_curve([0] * 10, 100, "global"))
    assert st["bass"] == 100                          # stored raw
    assert fake.applied[-1][1] == st["safe_limits"]["bass"]  # applied clamped


def test_guard_off_applies_raw_boost(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    asyncio.run(p.set_audio_enabled(True))
    st = asyncio.run(p.set_speaker_guard(False))
    assert st["guard"] is False
    st = asyncio.run(p.set_audio_bands([12] * 10, "global"))
    assert fake.applied[-1][0] == [12.0] * 10


def test_guard_does_not_clamp_headphone_route(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch, audio=_FakePipeWireEq(route="headphone"))
    asyncio.run(p.set_audio_enabled(True))
    st = asyncio.run(p.set_audio_bands([12] * 10, "global"))
    assert st["route"] == "headphone"
    assert fake.applied[-1][0] == [12.0] * 10  # guard is speaker-only


# --- spatial effects: crossfeed (headphone) + stereo width (speaker) ------------------

def test_spatial_defaults_in_state(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch)
    st = asyncio.run(p.get_audio_state())
    assert st["crossfeed"] == 0 and st["stereo_width"] == 50


def test_crossfeed_applies_on_headphone(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch, audio=_FakePipeWireEq(route="headphone"))
    asyncio.run(p.set_audio_enabled(True))
    st = asyncio.run(p.set_audio_crossfeed(70, "global"))
    assert st["crossfeed"] == 70
    assert fake.applied[-1][3] == 70          # crossfeed passed to set_gains
    assert fake.applied[-1][4] == 50          # width stays neutral on headphones


def test_crossfeed_ignored_on_speaker_route(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch, audio=_FakePipeWireEq(route="speaker"))
    asyncio.run(p.set_audio_enabled(True))
    st = asyncio.run(p.set_audio_crossfeed(70, "global"))
    assert fake.applied[-1][3] == 0           # not applied on speakers
    assert st["crossfeed"] == 0               # speaker route view reports neutral (route-exclusive)


def test_stereo_width_applies_on_speaker(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch, audio=_FakePipeWireEq(route="speaker"))
    asyncio.run(p.set_audio_enabled(True))
    st = asyncio.run(p.set_audio_stereo_width(80, "global"))
    assert st["stereo_width"] == 80
    assert fake.applied[-1][4] == 80          # width passed to set_gains
    assert fake.applied[-1][3] == 0           # crossfeed neutral on speakers


def test_stereo_width_ignored_on_headphone_route(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch, audio=_FakePipeWireEq(route="headphone"))
    asyncio.run(p.set_audio_enabled(True))
    st = asyncio.run(p.set_audio_stereo_width(80, "global"))
    assert fake.applied[-1][4] == 50          # neutral (unapplied) on headphones
    assert st["stereo_width"] == 50           # headphone route view reports neutral (route-exclusive)


def test_spatial_preserved_across_preset(tmp_path, monkeypatch):
    p, fake = _make_plugin(tmp_path, monkeypatch, audio=_FakePipeWireEq(route="headphone"))
    asyncio.run(p.set_audio_crossfeed(40, "global"))
    st = asyncio.run(p.apply_audio_preset("music", "global"))
    assert st["crossfeed"] == 40 and st["preset"] == "music"
