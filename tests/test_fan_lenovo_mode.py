"""Tests for the Legion Go S coarse fan-mode backend (LenovoFanModeBackend).

The Go S firmware exposes no writable temp→RPM curve; the only working control is
a coarse ``fan_mode`` node (VPC2004 / ideapad-style) taking 0/1/2 = quiet/balanced/
performance. Synthetic sysfs via tmp_path, mirroring test_fans_hwmon.py.
"""
import os

from fans.lenovo_mode import (
    LenovoFanModeBackend,
    PRESET_TO_MODE,
    _DEFAULT_MODE,
)


def _make_fan_mode_node(root, value="1"):
    """Create the VPC2004 fan_mode node under a synthetic sysfs root."""
    d = os.path.join(root, "sys/bus/platform/devices/VPC2004:00")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "fan_mode"), "w") as f:
        f.write(value)
    return os.path.join(d, "fan_mode")


class TestDetection:
    def test_unsupported_when_node_absent(self, tmp_path):
        b = LenovoFanModeBackend(root=str(tmp_path))
        assert b.supported is False

    def test_supported_when_node_present(self, tmp_path):
        _make_fan_mode_node(str(tmp_path))
        b = LenovoFanModeBackend(root=str(tmp_path))
        assert b.supported is True
        assert b.mode_based is True


class TestReadState:
    def test_reports_current_mode(self, tmp_path):
        _make_fan_mode_node(str(tmp_path), "2")
        b = LenovoFanModeBackend(root=str(tmp_path))
        st = b.read_state()
        assert st["supported"] is True
        assert st["mode_based"] is True
        assert st["mode"] == 2
        assert st["source"] == b.name

    def test_unsupported_state_shape(self, tmp_path):
        b = LenovoFanModeBackend(root=str(tmp_path))
        st = b.read_state()
        assert st["supported"] is False
        assert st["mode_based"] is True
        assert st["mode"] is None


class TestSetMode:
    def test_write_valid_mode_latches(self, tmp_path):
        node = _make_fan_mode_node(str(tmp_path), "1")
        b = LenovoFanModeBackend(root=str(tmp_path))
        res = b.set_mode(2)
        assert res["ok"] is True
        assert open(node).read().strip() == "2"
        assert b.read_state()["mode"] == 2

    def test_reject_out_of_range_mode(self, tmp_path):
        _make_fan_mode_node(str(tmp_path), "1")
        b = LenovoFanModeBackend(root=str(tmp_path))
        res = b.set_mode(3)
        assert res["ok"] is False
        # rejected write must not report the requested mode
        assert b.read_state()["mode"] == 1

    def test_readback_mismatch_reports_failure(self, tmp_path):
        # A node that silently refuses the write (readback stays put) => not ok.
        node = _make_fan_mode_node(str(tmp_path), "1")

        class _StuckBackend(LenovoFanModeBackend):
            def _write_mode(self, mode):
                return True  # pretend the write "succeeded" but the node won't move

        b = _StuckBackend(root=str(tmp_path))
        res = b.set_mode(2)
        assert res["ok"] is False
        assert open(node).read().strip() == "1"

    def test_unsupported_set_mode_degrades(self, tmp_path):
        b = LenovoFanModeBackend(root=str(tmp_path))
        assert b.set_mode(2)["ok"] is False


class TestFailSafe:
    def test_restore_auto_returns_to_default_mode(self, tmp_path):
        node = _make_fan_mode_node(str(tmp_path), "2")
        b = LenovoFanModeBackend(root=str(tmp_path))
        res = b.restore_auto()
        assert res["ok"] is True
        assert int(open(node).read().strip()) == _DEFAULT_MODE == 1

    def test_set_auto_returns_to_default_mode(self, tmp_path):
        node = _make_fan_mode_node(str(tmp_path), "0")
        b = LenovoFanModeBackend(root=str(tmp_path))
        b.set_auto(None)
        assert int(open(node).read().strip()) == _DEFAULT_MODE


class TestPresetMapping:
    def test_preset_to_mode_covers_the_three_presets(self):
        assert PRESET_TO_MODE == {"silent": 0, "balanced": 1, "performance": 2}

    def test_apply_preset_writes_mapped_mode(self, tmp_path):
        node = _make_fan_mode_node(str(tmp_path), "1")
        b = LenovoFanModeBackend(root=str(tmp_path))
        assert b.apply_preset("performance")["ok"] is True
        assert open(node).read().strip() == "2"
        assert b.apply_preset("silent")["ok"] is True
        assert open(node).read().strip() == "0"

    def test_apply_unknown_preset_falls_back_to_default(self, tmp_path):
        node = _make_fan_mode_node(str(tmp_path), "2")
        b = LenovoFanModeBackend(root=str(tmp_path))
        # custom/adaptive aren't representable as a coarse mode → default (balanced).
        assert b.apply_preset("custom")["ok"] is True
        assert int(open(node).read().strip()) == _DEFAULT_MODE

    def test_apply_curve_all_falls_back_to_default(self, tmp_path):
        # A canonical curve can't drive a coarse-mode fan; apply_curve_all keeps the
        # interface honest by settling on the default mode (never a fake curve).
        node = _make_fan_mode_node(str(tmp_path), "0")
        b = LenovoFanModeBackend(root=str(tmp_path))
        assert b.apply_curve_all([(40, 0), (95, 255)])["ok"] is True
        assert int(open(node).read().strip()) == _DEFAULT_MODE
