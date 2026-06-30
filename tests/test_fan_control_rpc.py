"""RPC-level tests for fan-curve control (get_fan_control, set_fan_curve, set_fan_auto).

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
# Tests: Null backend (no hwmon — default in tmp_path)
# ---------------------------------------------------------------------------

class TestFanControlRpcNull:
    @pytest.fixture
    def Plugin(self, tmp_path, monkeypatch):
        return _make_plugin_fixture(tmp_path, monkeypatch)

    def test_get_fan_control_returns_supported_false(self, Plugin):
        r = asyncio.run(Plugin().get_fan_control())
        assert r["supported"] is False
        assert r["fans"] == []

    def test_get_fan_control_has_source_and_pwm_max(self, Plugin):
        r = asyncio.run(Plugin().get_fan_control())
        assert "source" in r
        assert "pwm_max" in r

    def test_set_fan_curve_returns_ok_false_when_unsupported(self, Plugin):
        pts = [(i * 10, i * 25) for i in range(8)]
        r = asyncio.run(Plugin().set_fan_curve("cpu", pts))
        assert r["ok"] is False
        assert isinstance(r["detail"], str)

    def test_set_fan_auto_returns_ok_false_when_unsupported(self, Plugin):
        r = asyncio.run(Plugin().set_fan_auto(None))
        assert r["ok"] is False

    def test_set_fan_curve_invalid_args_returns_ok_false(self, Plugin):
        r = asyncio.run(Plugin().set_fan_curve(123, "not-a-list"))
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# Tests: Real AsusFanCurveBackend with synthetic sysfs
# ---------------------------------------------------------------------------

class TestFanControlRpcAsus:
    @pytest.fixture
    def asus_root(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        return tmp_path

    @pytest.fixture
    def Plugin(self, asus_root, monkeypatch):
        backend = AsusFanCurveBackend(root=str(asus_root))
        assert backend.supported
        return _make_plugin_fixture(asus_root, monkeypatch, fan_ctrl_override=backend)

    def test_get_fan_control_supported(self, Plugin):
        r = asyncio.run(Plugin().get_fan_control())
        assert r["supported"] is True
        assert r["source"] == "asus_custom_fan_curve"
        assert r["pwm_max"] == 255

    def test_get_fan_control_has_two_fans(self, Plugin):
        r = asyncio.run(Plugin().get_fan_control())
        keys = {f["key"] for f in r["fans"]}
        assert keys == {"cpu", "gpu"}

    def test_get_fan_control_each_fan_has_8_points(self, Plugin):
        r = asyncio.run(Plugin().get_fan_control())
        for fan in r["fans"]:
            assert len(fan["points"]) == 8

    def test_set_fan_curve_ok_true(self, Plugin):
        pts = [(i * 10, i * 25) for i in range(8)]
        r = asyncio.run(Plugin().set_fan_curve("cpu", pts))
        assert r["ok"] is True

    def test_set_fan_curve_sets_enable_to_1(self, Plugin, asus_root):
        pts = [(i * 10, i * 25) for i in range(8)]
        asyncio.run(Plugin().set_fan_curve("cpu", pts))
        enable_path = None
        for hwmon_dir in os.scandir(os.path.join(str(asus_root), "sys/class/hwmon")):
            enable_path = os.path.join(hwmon_dir.path, "pwm1_enable")
        assert enable_path and open(enable_path).read().strip() == "1"

    def test_set_fan_curve_unknown_key_returns_ok_false(self, Plugin):
        r = asyncio.run(Plugin().set_fan_curve("exhaust", [(i * 10, 100) for i in range(8)]))
        assert r["ok"] is False

    def test_set_fan_auto_restores_enable_2(self, Plugin, asus_root):
        pts = [(i * 10, i * 25) for i in range(8)]
        asyncio.run(Plugin().set_fan_curve("cpu", pts))
        asyncio.run(Plugin().set_fan_auto("cpu"))
        for hwmon_dir in os.scandir(os.path.join(str(asus_root), "sys/class/hwmon")):
            val = open(os.path.join(hwmon_dir.path, "pwm1_enable")).read().strip()
        assert val == "2"

    def test_set_fan_auto_none_restores_all_fans(self, Plugin, asus_root):
        pts = [(i * 10, i * 25) for i in range(8)]
        p = Plugin()
        asyncio.run(p.set_fan_curve("cpu", pts))
        asyncio.run(p.set_fan_curve("gpu", pts))
        asyncio.run(p.set_fan_auto(None))
        for hwmon_dir in os.scandir(os.path.join(str(asus_root), "sys/class/hwmon")):
            d = hwmon_dir.path
            assert open(os.path.join(d, "pwm1_enable")).read().strip() == "2"
            assert open(os.path.join(d, "pwm2_enable")).read().strip() == "2"

    def test_set_fan_curve_sanitizes_short_list(self, Plugin):
        # Fewer than 8 points — should pad + succeed
        r = asyncio.run(Plugin().set_fan_curve("gpu", [(30, 80), (70, 200)]))
        assert r["ok"] is True
