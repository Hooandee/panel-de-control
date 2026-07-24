"""RPC-level tests for fan-curve control (get_fan_curve_state, set_fan_preset,
set_fan_curve_points, set_fan_auto).

Uses the same Plugin fixture pattern as test_tdp_rpc.py — monkeypatches ``decky``
and reloads ``main`` so we get a real Plugin instance without live hardware.

Two scenarios are tested:
  A) Null backend (no chip found) — RPC calls degrade gracefully.
  B) Fake asus backend (wraps AsusFanCurveBackend with a tmp sysfs root).
"""
import asyncio
import importlib
import os
import sys
import types

import pytest

from fans.control import AsusFanCurveBackend


# ---------------------------------------------------------------------------
# Synthetic hwmon helpers (duplicated from test_fan_control for isolation)
# ---------------------------------------------------------------------------

def _make_asus_chip(root, idx=0):
    d = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    _w(d, "name", "asus_custom_fan_curve")
    for m in (1, 2):
        for k in range(1, 9):
            _w(d, f"pwm{m}_auto_point{k}_temp", str(40 + k * 5))
            _w(d, f"pwm{m}_auto_point{k}_pwm", str(30 + k * 15))
        _w(d, f"pwm{m}_enable", "2")
    return d


def _w(d, name, val):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(val)


# ---------------------------------------------------------------------------
# Shared fixture factory
# ---------------------------------------------------------------------------

def _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=None):
    """Bootstrap a Plugin instance with a fake decky module.

    If ``fan_ctrl_override`` is given it is injected as ``_fan_ctrl`` after
    ``_init()``; otherwise the default (NullFanBackend from no hwmon in
    tmp_path) is used.
    """
    fake_decky = types.ModuleType("decky")
    fake_decky.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake_decky.DECKY_USER = "deck"
    fake_decky.logger = types.SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
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

    if fan_ctrl_override is not None:
        original_init = main.Plugin._init

        def patched_init(self):
            original_init(self)
            self._fan_ctrl = fan_ctrl_override

        monkeypatch.setattr(main.Plugin, "_init", patched_init)

    return main.Plugin


# ---------------------------------------------------------------------------
# Tests: Null backend (no hwmon — default in tmp_path). The UI hides the editor
# when unsupported, but the RPCs must still degrade without raising.
# ---------------------------------------------------------------------------

class TestFanCurveRpcNull:
    @pytest.fixture
    def Plugin(self, tmp_path, monkeypatch):
        return _make_plugin_fixture(tmp_path, monkeypatch)

    def test_state_supported_false(self, Plugin):
        st = asyncio.run(Plugin().get_fan_curve_state())
        assert st["supported"] is False
        assert st["preset"] == "auto"
        assert {p["id"] for p in st["presets"]} == {"silent", "balanced", "performance"}

    def test_set_preset_degrades_without_raising(self, Plugin):
        st = asyncio.run(Plugin().set_fan_preset("balanced", "global", None))
        assert st["supported"] is False
        assert st["preset"] == "balanced"  # persisted even though hardware can't apply

    def test_fan_follow_global_toggle_keeps_own(self, Plugin):
        p = Plugin()
        asyncio.run(p.set_fan_preset("balanced", "global", None))
        asyncio.run(p.set_current_game("42"))
        asyncio.run(p.set_fan_preset("performance", "game", "42"))  # own
        assert asyncio.run(p.get_fan_curve_state())["preset"] == "performance"
        st = asyncio.run(p.set_fan_follow_global(True, "42"))
        assert st["follows_global"] is True and st["preset"] == "balanced"
        st = asyncio.run(p.set_fan_follow_global(False, "42"))
        assert st["follows_global"] is False and st["preset"] == "performance"

    def test_fan_follow_own_without_profile_seeds_from_global(self, Plugin):
        p = Plugin()
        asyncio.run(p.set_fan_preset("silent", "global", None))
        asyncio.run(p.set_current_game("99"))
        st = asyncio.run(p.set_fan_follow_global(False, "99"))
        assert st["follows_global"] is False
        assert st["has_game_profile"] is True and st["preset"] == "silent"

    def test_suggestion_unsupported_backend(self, Plugin):
        s = asyncio.run(Plugin().get_fan_suggestion("555"))
        assert s["available"] is False
        assert s["reason"] == "unsupported"


class _EcRpmBackend:
    """Stand-in for the Legion EC backend: no hwmon fan, but reads RPM over the EC."""
    supported = True
    name = "legion-go2-ec"

    def read_state(self):
        return {"supported": True, "source": self.name, "pwm_max": 255,
                "fans": [{"key": "fan", "enable": 2, "rpm": 2982, "points": []}]}

    def apply_curve_all(self, points):
        return {"ok": True, "detail": ""}

    def set_auto(self, fan_key=None):
        return {"ok": True, "detail": ""}

    def restore_auto(self):
        return {"ok": True, "detail": ""}


def test_get_fan_state_surfaces_ec_rpm_when_no_hwmon_fan(tmp_path, monkeypatch):
    # Legion Go 2: hwmon exposes no fan, but the control backend reads RPM over the
    # EC. The monitor must surface that real RPM instead of showing nothing.
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=_EcRpmBackend())
    st = asyncio.run(Plugin().get_fan_state())
    assert st["supported"] is True
    assert [f["rpm"] for f in st["fans"]] == [2982]

    def test_set_auto_degrades(self, Plugin):
        st = asyncio.run(Plugin().set_fan_auto("global", None))
        assert st["preset"] == "auto"

    def test_unknown_preset_is_noop(self, Plugin):
        st = asyncio.run(Plugin().set_fan_preset("nonsense", "global", None))
        assert st["preset"] == "auto"


# ---------------------------------------------------------------------------
# Tests: Real AsusFanCurveBackend with synthetic sysfs
# ---------------------------------------------------------------------------

class TestFanCurveRpcAsus:
    @pytest.fixture
    def asus_root(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        return tmp_path

    @pytest.fixture
    def Plugin(self, asus_root, monkeypatch):
        backend = AsusFanCurveBackend(root=str(asus_root))
        assert backend.supported
        return _make_plugin_fixture(asus_root, monkeypatch, fan_ctrl_override=backend)

    def _enables(self, asus_root):
        for hwmon_dir in os.scandir(os.path.join(str(asus_root), "sys/class/hwmon")):
            d = hwmon_dir.path
            return (
                open(os.path.join(d, "pwm1_enable")).read().strip(),
                open(os.path.join(d, "pwm2_enable")).read().strip(),
            )
        return (None, None)

    def test_default_state_is_auto(self, Plugin):
        st = asyncio.run(Plugin().get_fan_curve_state())
        assert st["supported"] is True
        assert st["source"] == "asus_custom_fan_curve"
        assert st["preset"] == "auto"
        assert st["points"] is None

    def test_set_preset_applies_to_all_fans(self, Plugin, asus_root):
        st = asyncio.run(Plugin().set_fan_preset("balanced", "global", None))
        assert st["preset"] == "balanced"
        assert len(st["points"]) == 8
        assert self._enables(asus_root) == ("1", "1")  # both fans manual

    def test_set_custom_points(self, Plugin):
        pts = [[40, 0], [50, 30], [60, 60], [70, 95], [80, 135], [85, 175], [90, 215], [95, 255]]
        st = asyncio.run(Plugin().set_fan_curve_points(pts, "global", None))
        assert st["preset"] == "custom"

    def test_set_auto_returns_fans_to_firmware(self, Plugin, asus_root):
        asyncio.run(Plugin().set_fan_preset("performance", "global", None))
        st = asyncio.run(Plugin().set_fan_auto("global", None))
        assert st["preset"] == "auto"
        assert self._enables(asus_root) == ("2", "2")

    def test_game_scope_creates_profile(self, Plugin):
        p = Plugin()
        asyncio.run(p.set_current_game("123"))
        st = asyncio.run(p.set_fan_preset("silent", "game", "123"))
        assert st["preset"] == "silent"
        assert st["has_game_profile"] is True
        assert st["appid"] == "123"
        assert st["global_preset"] == "auto"  # global untouched

    def _feed_band(self, p, appid):
        # Feed realistic 5 s samples across a 58–82 °C band. The store now DECAYS
        # old dwell with in-game time (~30 min half-life), so weighted dwell tops
        # out below wall-clock dwell — feed ~60 min of real play to clear the
        # 30-min gate. (A single huge-dt sample would just fade itself away.)
        for temp, secs in [(58, 720), (64, 720), (70, 900), (76, 720), (82, 720)]:
            for _ in range(secs // 5):
                p._telemetry.add_sample(
                    appid, {"pl1": 15, "temp_cpu": temp, "temp_gpu": temp - 4}, dt=5.0)

    def test_suggestion_available_with_good_data(self, Plugin):
        p = Plugin()
        asyncio.run(p.set_current_game("555"))
        self._feed_band(p, "555")
        s = asyncio.run(p.get_fan_suggestion("555"))
        assert s["available"] is True
        assert s["reason"] == "ok"
        assert set(s["curves"]) == {"quiet", "balanced", "cool"}
        assert all(len(c) == 8 for c in s["curves"].values())
        assert s["minutes"] >= 30
        assert s["band"]["floor"] <= s["band"]["peak"]

    def test_suggestion_too_few_with_little_data(self, Plugin):
        p = Plugin()
        asyncio.run(p.set_current_game("556"))
        p._telemetry.add_sample("556", {"pl1": 15, "temp_cpu": 60, "temp_gpu": 55}, dt=100)
        s = asyncio.run(p.get_fan_suggestion("556"))
        assert s["available"] is False
        assert s["reason"] == "too_few"
        assert s["minutes"] >= 1

    def test_suggestion_no_game(self, Plugin):
        s = asyncio.run(Plugin().get_fan_suggestion(None))
        assert s["available"] is False
        assert s["reason"] == "no_game"

    def test_suggestion_disabled_when_telemetry_off(self, Plugin):
        p = Plugin()
        asyncio.run(p.set_telemetry_enabled(False))
        s = asyncio.run(p.get_fan_suggestion("555"))
        assert s["available"] is False
        assert s["reason"] == "disabled"

    def test_adaptive_mode_applies_learned_curve_to_hardware(self, Plugin, asus_root):
        # Selecting Adaptive with enough real data drives the learned curve → both
        # fans flip to manual (enable=1), like any applied curve.
        p = Plugin()
        asyncio.run(p.set_current_game("555"))
        self._feed_band(p, "555")
        st = asyncio.run(p.set_fan_adaptive("game", "555"))
        assert st["preset"] == "adaptive"
        assert st["points"] is None  # adaptive stores no points (computed live)
        assert self._enables(asus_root) == ("1", "1")

    def test_adaptive_mode_no_data_stays_firmware_auto(self, Plugin, asus_root):
        # adaptive with no learned data leaves the fans on firmware auto.
        p = Plugin()
        asyncio.run(p.set_current_game("777"))
        st = asyncio.run(p.set_fan_adaptive("game", "777"))
        assert st["preset"] == "adaptive"
        assert self._enables(asus_root) == ("2", "2")

    def test_custom_points_sanitized_before_store(self, Plugin):
        # Drag every point (incl. the hottest) to 0 duty. The backend safety floor
        # must be reflected in the STORED + returned state, not just at apply time —
        # otherwise the UI would show a curve the hardware silently overrides.
        flat_zero = [[40, 0], [50, 0], [60, 0], [70, 0], [80, 0], [85, 0], [90, 0], [95, 0]]
        st = asyncio.run(Plugin().set_fan_curve_points(flat_zero, "global", None))
        assert st["preset"] == "custom"
        assert len(st["points"]) == 8
        assert st["points"][-1][1] >= 76  # hottest point floored, honestly reflected


# ---------------------------------------------------------------------------
# Tests: read-only firmware curve (MSI Claw EC) — write backend unsupported but
# the firmware curve is legible and shown informationally.
# ---------------------------------------------------------------------------

class TestFirmwareCurveReadOnly:
    def _fixture(self, tmp_path, monkeypatch, ec_reader):
        from fans.control import NullFanBackend
        Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=NullFanBackend())
        original_init = Plugin._init

        def patched_init(self):
            original_init(self)
            self._fan_ctrl = NullFanBackend()
            self._ec_curve = ec_reader

        monkeypatch.setattr(Plugin, "_init", patched_init)
        return Plugin

    def test_read_only_curve_surfaced_when_write_unsupported(self, tmp_path, monkeypatch):
        from fans.ec_curve import EcFanCurveReader

        buf = bytearray(256)
        buf[0x6A:0x70] = bytes([50, 60, 70, 80, 88, 88])
        buf[0x73:0x79] = bytes([40, 49, 58, 67, 75, 75])
        reader = EcFanCurveReader(read_bytes=lambda: bytes(buf))
        Plugin = self._fixture(tmp_path, monkeypatch, reader)

        st = asyncio.run(Plugin().get_fan_curve_state())
        assert st["supported"] is False
        assert st["firmware_points"] == [
            {"temp": 50, "pct": 40}, {"temp": 60, "pct": 49}, {"temp": 70, "pct": 58},
            {"temp": 80, "pct": 67}, {"temp": 88, "pct": 75}, {"temp": 88, "pct": 75},
        ]

    def test_no_curve_when_ec_unreadable(self, tmp_path, monkeypatch):
        from fans.ec_curve import EcFanCurveReader

        reader = EcFanCurveReader(read_bytes=lambda: None)
        Plugin = self._fixture(tmp_path, monkeypatch, reader)
        st = asyncio.run(Plugin().get_fan_curve_state())
        assert st["firmware_points"] is None

    def test_no_reader_leaves_state_unchanged(self, tmp_path, monkeypatch):
        Plugin = self._fixture(tmp_path, monkeypatch, None)
        st = asyncio.run(Plugin().get_fan_curve_state())
        assert st["firmware_points"] is None


class _ResetBackend:
    """Records calls; restore_auto returns a configurable ok so the RPC's honest
    reset_ok can be asserted both ways."""
    supported = True
    name = "legion-go-s-ec"

    def __init__(self, release_ok=True, apply_ok=True):
        self.release_ok = release_ok
        self.apply_ok = apply_ok
        self.calls = []

    def read_state(self):
        return {"supported": True, "source": self.name, "pwm_max": 255,
                "fans": [{"key": "fan", "enable": 2, "rpm": 1900, "points": []}]}

    def apply_curve_all(self, points):
        self.calls.append("apply")
        return {"ok": self.apply_ok, "detail": ""}

    def set_auto(self, fan_key=None):
        self.calls.append("set_auto")
        return {"ok": self.release_ok, "detail": ""}

    def restore_auto(self):
        self.calls.append("restore_auto")
        return {"ok": self.release_ok, "detail": ""}


def test_reset_fan_control_reports_release_success(tmp_path, monkeypatch):
    backend = _ResetBackend(release_ok=True)
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=backend)
    p = Plugin()
    asyncio.run(p.set_fan_preset("performance", "global", None))
    backend.calls.clear()
    st = asyncio.run(p.reset_fan_control())
    assert "restore_auto" in backend.calls
    assert st["supported"] is True
    assert st["reset_ok"] is True


def test_reset_fan_control_reports_release_failure(tmp_path, monkeypatch):
    # The release did not land — the RPC must say so, never a fake success.
    backend = _ResetBackend(release_ok=False)
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=backend)
    p = Plugin()
    st = asyncio.run(p.reset_fan_control())
    assert st["reset_ok"] is False


class _MalformedResetBackend(_ResetBackend):
    """restore_auto returns a malformed value (no/absent 'ok'). The RPC must not
    read that as success."""

    def __init__(self, ret):
        super().__init__()
        self._ret = ret

    def restore_auto(self):
        self.calls.append("restore_auto")
        return self._ret


@pytest.mark.parametrize("ret", [{}, None, {"detail": "x"}])
def test_reset_fan_control_malformed_release_is_not_success(tmp_path, monkeypatch, ret):
    backend = _MalformedResetBackend(ret)
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=backend)
    st = asyncio.run(Plugin().reset_fan_control())
    assert st["reset_ok"] is False


def test_state_resettable_true_for_software_loop_backend(tmp_path, monkeypatch):
    # A software-loop backend (Deck / EC / generic PWM) can wedge → expose a reset.
    backend = _ResetBackend()
    backend.resettable = True
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=backend)
    assert asyncio.run(Plugin().get_fan_curve_state())["resettable"] is True


def test_state_resettable_false_for_hardware_curve_backend(tmp_path, monkeypatch):
    # A hardware-curve backend (ASUS/MSI) or Null doesn't wedge → no reset offered.
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch)  # NullFanBackend
    assert asyncio.run(Plugin().get_fan_curve_state())["resettable"] is False


def test_reset_fan_control_reestablishes_the_stored_curve(tmp_path, monkeypatch):
    # After releasing, the reset must re-apply the stored curve (awaited), not just
    # release — otherwise a manual curve would silently drop to firmware auto.
    backend = _ResetBackend(release_ok=True)
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=backend)
    p = Plugin()
    asyncio.run(p.set_fan_preset("performance", "global", None))
    backend.calls.clear()
    asyncio.run(p.reset_fan_control())
    assert "restore_auto" in backend.calls
    assert "apply" in backend.calls  # stored curve re-established


def test_reset_ok_false_when_reapply_refuses(tmp_path, monkeypatch):
    # Released fine, but the stored curve couldn't be re-established → reset_ok must
    # be False, so "Control reiniciado" never shows on a still-wedged fan.
    backend = _ResetBackend(release_ok=True, apply_ok=False)
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=backend)
    p = Plugin()
    asyncio.run(p.set_fan_preset("performance", "global", None))  # a curve profile
    st = asyncio.run(p.reset_fan_control())
    assert st["reset_ok"] is False


class _MalformedReapplyBackend(_ResetBackend):
    def apply_curve_all(self, points):
        self.calls.append("apply")
        return {}  # malformed: no "ok" key


def test_reset_ok_false_when_reapply_malformed(tmp_path, monkeypatch):
    # A malformed re-apply response (no "ok") must not ride an optimistic default.
    backend = _MalformedReapplyBackend(release_ok=True)
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=backend)
    p = Plugin()
    asyncio.run(p.set_fan_preset("performance", "global", None))
    st = asyncio.run(p.reset_fan_control())
    assert st["reset_ok"] is False


class _MaxBackend:
    """Legion Go original GZFD stand-in exposing the full-blast ('a tope') control."""
    supported = True
    supports_max = True
    name = "legion-acpi-gzfd"

    def __init__(self):
        self.max_calls = []
        self.curve_calls = []

    def read_state(self):
        return {"supported": True, "source": self.name, "pwm_max": 255, "fans": []}

    def set_max(self, on):
        self.max_calls.append(bool(on))
        return {"ok": True, "detail": ""}

    def set_auto(self, fan_key=None):
        return {"ok": True, "detail": ""}

    def apply_curve_all(self, points):
        self.curve_calls.append(points)
        return {"ok": True, "detail": ""}

    def restore_auto(self):
        return {"ok": True, "detail": ""}


def test_fan_curve_state_exposes_max_flags(tmp_path, monkeypatch):
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=_MaxBackend())
    st = asyncio.run(Plugin().get_fan_curve_state())
    assert st["max_available"] is True
    assert st["max_enabled"] is False


def test_set_fan_max_drives_backend(tmp_path, monkeypatch):
    backend = _MaxBackend()
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=backend)
    p = Plugin()
    st = asyncio.run(p.set_fan_max(True))
    assert st["max_enabled"] is True
    assert backend.max_calls == [True]
    assert asyncio.run(p.get_fan_max()) is True


def test_set_fan_max_noop_on_backend_without_support(tmp_path, monkeypatch):
    # The Null-ish default backend (no set_max) must not raise; state stays off.
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch)
    st = asyncio.run(Plugin().set_fan_max(True))
    assert st["max_enabled"] is False


def test_reapply_reasserts_max_and_skips_curve_when_fan_max_on(tmp_path, monkeypatch):
    # "A tope" ON must survive a game change / adaptive re-fit: _reapply re-asserts the
    # override and does NOT rewrite the curve (which would silently end full-blast).
    backend = _MaxBackend()
    Plugin = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=backend)
    p = Plugin()
    asyncio.run(p.get_fan_curve_state())   # runs _init (sets _settings, _fan_curves)
    p._fan_max = True
    assert p._reapply_fans_sync() is True
    assert backend.max_calls[-1] is True
    assert backend.curve_calls == []
