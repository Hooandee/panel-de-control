"""Fan curves "Juntos / Por separado" (#1069): per-channel store model, ASUS two-table
backend with synthetic hwmon, and the backends that must stay joined."""
import asyncio
import os

import pytest

from fan_curves import FanCurveStore
from fans.control import (
    AsusFanCurveBackend,
    HwmonCurveBackend,
    LegionWmiFanBackend,
    MsiFanCurveBackend,
    NullFanBackend,
)
from fans.fremont import FremontFanBackend
from fans.generic_pwm import GenericPwmFanBackend
from fans.software_loop import SteamDeckFanBackend

from test_fan_control import _make_asus_chip, _r, _w
from test_fan_control_legion_wmi import _make_legion_chip
from test_fan_control_msi import _make_msi_chip

BALANCED = [[40, 0], [50, 30], [60, 60], [70, 95], [80, 135], [85, 175], [90, 215], [95, 255]]
SILENT = [[40, 0], [50, 0], [60, 20], [70, 40], [80, 80], [85, 120], [90, 160], [95, 255]]
CPU_HIGH = [[40, 100], [50, 120], [60, 140], [70, 160], [80, 180], [85, 200], [90, 220], [95, 255]]
GPU_LOW = [[40, 0], [50, 10], [60, 20], [70, 30], [80, 40], [85, 60], [90, 100], [95, 255]]


def _store(tmp_path):
    return FanCurveStore(str(tmp_path / "fan_curves.json"))


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class TestStoreSplit:
    def test_default_is_joined_and_legacy_profiles_load_unchanged(self, tmp_path):
        (tmp_path / "fan_curves.json").write_text(
            '{"global": {"preset": "balanced", "points": %s}, "games": {}}' % BALANCED)
        s = _store(tmp_path)
        assert s.is_split(None) is False
        assert s.split_state(None) is None
        assert s.effective(None) == {"preset": "balanced", "points": BALANCED}

    def test_activating_seeds_both_channels_with_current_curve(self, tmp_path):
        s = _store(tmp_path)
        s.set_preset("global", "balanced", BALANCED)
        s.set_split("global", True)
        preset, by_channel = s.split_state(None)
        assert preset == "balanced"
        assert by_channel == {"cpu": BALANCED, "gpu": BALANCED}
        assert by_channel["cpu"] is not by_channel["gpu"]

    def test_activating_from_auto_stays_auto(self, tmp_path):
        s = _store(tmp_path)
        s.set_split("global", True)
        assert s.split_state(None) == ("auto", None)

    def test_activating_with_explicit_seed_becomes_custom(self, tmp_path):
        s = _store(tmp_path)
        s.set_adaptive("global")
        s.set_split("global", True, seed_points=SILENT)
        assert s.split_state(None) == ("custom", {"cpu": SILENT, "gpu": SILENT})
        assert s.is_adaptive(None) is False  # adaptive only exists joined

    def test_channels_are_edited_independently(self, tmp_path):
        s = _store(tmp_path)
        s.set_preset("global", "balanced", BALANCED)
        s.set_split("global", True)
        s.set_split_custom("global", "cpu", CPU_HIGH)
        s.set_split_custom("global", "gpu", GPU_LOW)
        assert s.split_state(None) == ("custom", {"cpu": CPU_HIGH, "gpu": GPU_LOW})

    def test_editing_one_channel_keeps_the_other_curve(self, tmp_path):
        s = _store(tmp_path)
        s.set_preset("global", "silent", SILENT)
        s.set_split("global", True)
        s.set_split_custom("global", "gpu", GPU_LOW)
        assert s.split_state(None) == ("custom", {"cpu": SILENT, "gpu": GPU_LOW})

    def test_preset_applies_to_both_channels_in_split(self, tmp_path):
        s = _store(tmp_path)
        s.set_split("global", True)
        s.set_split_custom("global", "cpu", CPU_HIGH)
        s.set_split_preset("global", "silent", SILENT)
        assert s.split_state(None) == ("silent", {"cpu": SILENT, "gpu": SILENT})

    def test_manual_pair_is_remembered_outside_custom(self, tmp_path):
        s = _store(tmp_path)
        s.set_split("global", True, seed_points=BALANCED)
        s.set_split_custom("global", "cpu", CPU_HIGH)
        s.set_split_custom("global", "gpu", GPU_LOW)
        s.set_split_preset("global", "silent", SILENT)
        assert s.effective(None)["custom_points_by_channel"] == {"cpu": CPU_HIGH, "gpu": GPU_LOW}

    def test_returning_to_joined_keeps_the_single_curve(self, tmp_path):
        # Regression shape of #1334: the stored manual curve must not be replaced.
        s = _store(tmp_path)
        s.set_custom("global", BALANCED)
        s.set_split("global", True)
        s.set_split_custom("global", "cpu", CPU_HIGH)
        s.set_split_custom("global", "gpu", GPU_LOW)
        s.set_split("global", False)
        assert s.is_split(None) is False
        eff = s.effective(None)
        assert eff["preset"] == "custom" and eff["points"] == BALANCED
        assert "points_by_channel" not in eff and "split" not in eff

    def test_joined_setters_keep_per_channel_state(self, tmp_path):
        s = _store(tmp_path)
        s.set_split("global", True, seed_points=BALANCED)
        s.set_split_custom("global", "cpu", CPU_HIGH)
        s.set_split("global", False)
        s.set_preset("global", "silent", SILENT)  # joined edit afterwards
        s.set_split("global", True)
        assert s.effective(None)["custom_points_by_channel"]["cpu"] == CPU_HIGH

    def test_joined_manual_memory_survives_a_split_round_trip(self, tmp_path):
        s = _store(tmp_path)
        s.set_custom("global", BALANCED)
        s.set_preset("global", "silent", SILENT)  # custom_points = BALANCED
        s.set_split("global", True)
        s.set_split_custom("global", "cpu", CPU_HIGH)
        s.set_split("global", False)
        assert s.effective(None)["custom_points"] == BALANCED

    def test_persists_and_reloads(self, tmp_path):
        s = _store(tmp_path)
        s.set_split("global", True, seed_points=BALANCED)
        s.set_split_custom("global", "gpu", GPU_LOW)
        again = _store(tmp_path)
        assert again.split_state(None)[0] == "custom"
        assert again.split_state(None)[1]["gpu"] == GPU_LOW

    def test_corrupt_split_data_falls_back_to_auto_split(self, tmp_path):
        (tmp_path / "fan_curves.json").write_text(
            '{"global": {"preset": "custom", "points": %s, "split": true,'
            ' "split_preset": "custom", "points_by_channel": {"cpu": [[1, 2]]}}, "games": {}}' % BALANCED)
        assert _store(tmp_path).split_state(None) == ("auto", None)

    def test_game_scope_inherits_and_isolates(self, tmp_path):
        s = _store(tmp_path)
        s.set_split("global", True, seed_points=BALANCED)
        assert s.is_split_scope("game", "7") is True
        s.set_split_custom("game", "cpu", CPU_HIGH, appid="7")
        assert s.split_state("7")[1]["cpu"] == CPU_HIGH
        assert s.split_state(None)[1]["cpu"] == BALANCED
        s.set_split("game", False, appid="7")
        assert s.is_split("7") is False and s.is_split(None) is True


# ---------------------------------------------------------------------------
# ASUS backend with synthetic hwmon
# ---------------------------------------------------------------------------

def _asus(tmp_path):
    d = _make_asus_chip(str(tmp_path))
    backend = AsusFanCurveBackend(root=str(tmp_path))
    return backend, d


def _table(d, index):
    return [(int(_r(d, f"pwm{index}_auto_point{k}_temp")), int(_r(d, f"pwm{index}_auto_point{k}_pwm")))
            for k in range(1, 9)]


class TestAsusApplyCurves:
    def test_split_is_available_with_two_channels(self, tmp_path):
        backend, _ = _asus(tmp_path)
        state = backend.read_state()
        assert state["split_available"] is True
        assert state["channels"] == ["cpu", "gpu"]

    def test_writes_a_different_whole_table_per_channel(self, tmp_path):
        backend, d = _asus(tmp_path)
        res = backend.apply_curves({"cpu": CPU_HIGH, "gpu": GPU_LOW})
        assert res["ok"] is True
        assert _table(d, 1) == [tuple(p) for p in CPU_HIGH]
        assert _table(d, 2) == [tuple(p) for p in GPU_LOW]
        assert _r(d, "pwm1_enable") == "1" and _r(d, "pwm2_enable") == "1"

    def test_inverted_round(self, tmp_path):
        # pwm1 high / pwm2 low, then the opposite: tables follow the channel, never the order.
        backend, d = _asus(tmp_path)
        assert backend.apply_curves({"cpu": CPU_HIGH, "gpu": GPU_LOW})["ok"]
        assert backend.apply_curves({"cpu": GPU_LOW, "gpu": CPU_HIGH})["ok"]
        assert _table(d, 1) == [tuple(p) for p in GPU_LOW]
        assert _table(d, 2) == [tuple(p) for p in CPU_HIGH]

    def test_write_failure_on_second_channel_returns_both_to_auto(self, tmp_path, monkeypatch):
        backend, d = _asus(tmp_path)
        import fans.control as control
        real = control._write

        def flaky(path, value):
            if "pwm2_auto_point3_pwm" in path:
                return False
            return real(path, value)

        monkeypatch.setattr(control, "_write", flaky)
        res = backend.apply_curves({"cpu": CPU_HIGH, "gpu": GPU_LOW})
        assert res["ok"] is False
        assert res["failed_channels"] == ["gpu"]
        assert res["released"] is True
        assert _r(d, "pwm1_enable") == "2" and _r(d, "pwm2_enable") == "2"

    def test_readback_mismatch_counts_as_failure_and_releases(self, tmp_path, monkeypatch):
        backend, d = _asus(tmp_path)
        import fans.control as control
        real = control._write

        def clamp_cpu(path, value):  # the kernel silently stores a different value
            if path.endswith("pwm1_auto_point5_pwm"):
                return real(path, "1")
            return real(path, value)

        monkeypatch.setattr(control, "_write", clamp_cpu)
        res = backend.apply_curves({"cpu": CPU_HIGH, "gpu": GPU_LOW})
        assert res["ok"] is False and res["failed_channels"] == ["cpu"]
        assert _r(d, "pwm1_enable") == "2" and _r(d, "pwm2_enable") == "2"

    def test_missing_channel_curve_fails_and_releases(self, tmp_path):
        backend, d = _asus(tmp_path)
        res = backend.apply_curves({"cpu": CPU_HIGH})
        assert res["ok"] is False
        assert _r(d, "pwm1_enable") == "2" and _r(d, "pwm2_enable") == "2"

    def test_single_channel_chip_has_no_split(self, tmp_path):
        d = _make_asus_chip(str(tmp_path))
        os.remove(os.path.join(d, "pwm2_enable"))
        backend = AsusFanCurveBackend(root=str(tmp_path))
        assert backend.read_state()["split_available"] is False
        assert backend.apply_curves({"cpu": CPU_HIGH, "gpu": GPU_LOW})["ok"] is False

    def test_apply_curve_all_is_unchanged(self, tmp_path):
        backend, d = _asus(tmp_path)
        assert backend.apply_curve_all(BALANCED)["ok"] is True
        assert _table(d, 1) == _table(d, 2)


# ---------------------------------------------------------------------------
# Backends that must stay "juntos"
# ---------------------------------------------------------------------------

class TestJoinedBackendsUnchanged:
    def test_msi_has_no_split(self, tmp_path):
        _make_msi_chip(str(tmp_path))
        backend = MsiFanCurveBackend(root=str(tmp_path))
        assert backend.supported and backend.split_available is False
        assert backend.read_state()["split_available"] is False
        assert backend.apply_curves({"cpu": CPU_HIGH, "gpu": GPU_LOW})["ok"] is False

    def test_legion_wmi_has_no_split(self, tmp_path):
        _make_legion_chip(str(tmp_path))
        backend = LegionWmiFanBackend(root=str(tmp_path))
        assert backend.supported and backend.split_available is False
        assert backend.read_state()["split_available"] is False

    def test_null_has_no_split(self):
        backend = NullFanBackend()
        assert "split_available" not in backend.read_state()
        assert getattr(backend, "split_available", False) is False
        assert backend.apply_curves({})["ok"] is False

    @pytest.mark.parametrize("cls", [SteamDeckFanBackend, FremontFanBackend, GenericPwmFanBackend])
    def test_other_families_never_advertise_split(self, cls):
        assert getattr(cls, "split_available", False) is False
        assert not hasattr(cls, "apply_curves")

    def test_plain_hwmon_base_with_fixed_temps_is_joined(self, tmp_path):
        _make_msi_chip(str(tmp_path))
        base = HwmonCurveBackend("msi_wmi_platform", n_points=6, fixed_temps=(0, 50, 60, 70, 80, 88),
                                 root=str(tmp_path))
        assert base.split_available is False


# ---------------------------------------------------------------------------
# RPC end to end (Plugin + ASUS synthetic chip)
# ---------------------------------------------------------------------------

from test_fan_control_rpc import _make_plugin_fixture  # noqa: E402


class TestSplitRpc:
    @pytest.fixture
    def asus_root(self, tmp_path):
        _make_asus_chip(str(tmp_path))
        return tmp_path

    @pytest.fixture
    def Plugin(self, asus_root, monkeypatch):
        backend = AsusFanCurveBackend(root=str(asus_root))
        return _make_plugin_fixture(asus_root, monkeypatch, fan_ctrl_override=backend)

    def _hw(self, asus_root):
        d = os.path.join(str(asus_root), "sys/class/hwmon/hwmon0")
        return d

    def test_state_advertises_split_capability(self, Plugin):
        st = asyncio.run(Plugin().get_fan_curve_state())
        assert st["split_available"] is True and st["split"] is False and st["channels"] == []

    def test_split_edit_writes_distinct_tables_and_back_keeps_joined(self, Plugin, asus_root):
        p = Plugin()
        asyncio.run(p.set_fan_preset("balanced", "global", None))
        st = asyncio.run(p.set_fan_split(True, "global", None))
        assert st["split"] is True and st["preset"] == "balanced"
        assert [c["key"] for c in st["channels"]] == ["cpu", "gpu"]
        assert st["channels"][0]["points"] == st["channels"][1]["points"]
        asyncio.run(p.set_fan_curve_points(CPU_HIGH, "global", None, "cpu"))
        st = asyncio.run(p.set_fan_curve_points(GPU_LOW, "global", None, "gpu"))
        assert st["preset"] == "custom"
        d = self._hw(asus_root)
        assert _table(d, 1) == [tuple(q) for q in CPU_HIGH]
        assert _table(d, 2) == [tuple(q) for q in GPU_LOW]
        st = asyncio.run(p.set_fan_split(False, "global", None))
        assert st["split"] is False and st["preset"] == "balanced"
        assert _table(d, 1) == _table(d, 2)

    def test_adaptive_is_refused_while_split(self, Plugin):
        p = Plugin()
        asyncio.run(p.set_fan_preset("silent", "global", None))
        asyncio.run(p.set_fan_split(True, "global", None))
        st = asyncio.run(p.set_fan_adaptive("global", None))
        assert st["split"] is True and st["preset"] == "silent"

    def test_failed_channel_write_releases_both_fans(self, Plugin, asus_root, monkeypatch):
        p = Plugin()
        asyncio.run(p.set_fan_preset("balanced", "global", None))
        asyncio.run(p.set_fan_split(True, "global", None))
        import fans.control as control
        real = control._write
        monkeypatch.setattr(control, "_write",
                            lambda path, v: False if "pwm2_auto_point2_pwm" in path else real(path, v))
        asyncio.run(p.set_fan_curve_points(CPU_HIGH, "global", None, "cpu"))
        d = self._hw(asus_root)
        assert _r(d, "pwm1_enable") == "2" and _r(d, "pwm2_enable") == "2"
        assert p._fan_apply_confirmed is False

    def test_split_auto_returns_to_firmware(self, Plugin, asus_root):
        p = Plugin()
        asyncio.run(p.set_fan_preset("balanced", "global", None))
        asyncio.run(p.set_fan_split(True, "global", None))
        st = asyncio.run(p.set_fan_auto("global", None))
        assert st["preset"] == "auto" and st["split"] is True
        assert _r(self._hw(asus_root), "pwm1_enable") == "2"

    def test_diagnostics_expose_split_fields(self, Plugin):
        p = Plugin()
        asyncio.run(p.set_fan_preset("balanced", "global", None))
        st = asyncio.run(p.set_fan_split(True, "global", None))
        assert st["points_by_channel"]["cpu"] == st["points_by_channel"]["gpu"]
        assert "split" in st and "split_available" in st

    def test_split_refused_when_backend_is_joined_only(self, tmp_path, monkeypatch):
        _make_msi_chip(str(tmp_path))
        backend = MsiFanCurveBackend(root=str(tmp_path))
        P = _make_plugin_fixture(tmp_path, monkeypatch, fan_ctrl_override=backend)
        p = P()
        asyncio.run(p.set_fan_preset("balanced", "global", None))
        st = asyncio.run(p.set_fan_split(True, "global", None))
        assert st["split_available"] is False and st["split"] is False
