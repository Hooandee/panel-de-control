"""Steam Deck software-loop fan backend (steamdeck_hwmon: fan1_target RPM +
re-assert). Synthetic sysfs; the asyncio loop itself isn't exercised — the
testable seams are target_for_temp (pure), the immediate apply, and release."""
import os

from fans.software_loop import SteamDeckFanBackend
from fans.control import select_fan_backend, NullFanBackend


def _w(d, name, val):
    with open(os.path.join(d, name), "w") as f:
        f.write(str(val))


def _r(d, name):
    with open(os.path.join(d, name)) as f:
        return f.read().strip()


def _make_deck_chip(root, idx=0, board="Jupiter"):
    d = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    _w(d, "name", "steamdeck_hwmon")
    _w(d, "fan1_input", "1500")
    _w(d, "fan1_target", "1500")
    return d


CURVE = [(40, 0), (50, 30), (60, 60), (70, 95), (80, 135), (85, 175), (90, 215), (95, 255)]


def _backend(root, temp=70.0):
    return SteamDeckFanBackend(root=str(root), temp_fn=lambda: temp)


class TestSteamDeckBackend:
    def test_supported_when_chip_present(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        assert _backend(tmp_path).supported is True

    def test_unsupported_without_chip(self, tmp_path):
        assert _backend(tmp_path).supported is False

    def test_read_state_reports_source(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        st = _backend(tmp_path).read_state()
        assert st["supported"] is True
        assert st["source"] == "steamdeck_hwmon"

    def test_target_for_temp_monotonic_and_in_rpm_range(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        b = _backend(tmp_path)
        b.apply_curve_all(CURVE)
        lo, hi = b.target_for_temp(45), b.target_for_temp(90)
        assert 0 <= lo <= hi <= b.max_rpm
        assert hi > lo

    def test_apply_writes_positive_target_and_switches_to_manual(self, tmp_path):
        d = _make_deck_chip(str(tmp_path))
        b = _backend(tmp_path, temp=85.0)
        res = b.apply_curve_all(CURVE)
        assert res["ok"] is True
        assert int(_r(d, "fan1_target")) == b.target_for_temp(85.0)
        assert int(_r(d, "fan1_target")) > 0

    def test_zero_duty_curve_does_not_write_release_sentinel(self, tmp_path):
        # A curve with 0% duty at cool temps must still DRIVE (>=1), never write 0 —
        # 0 means "release to firmware", which would silently drop manual control.
        d = _make_deck_chip(str(tmp_path))
        b = _backend(tmp_path, temp=40.0)  # 40C → CURVE duty 0
        b.apply_curve_all(CURVE)
        assert b.target_for_temp(40.0) >= 1
        assert int(_r(d, "fan1_target")) >= 1

    def test_set_auto_releases_to_firmware_with_zero(self, tmp_path):
        d = _make_deck_chip(str(tmp_path))
        b = _backend(tmp_path)
        b.apply_curve_all(CURVE)
        b.set_auto(None)
        assert int(_r(d, "fan1_target")) == 0

    def test_factory_selects_deck(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        backend = select_fan_backend(None, root=str(tmp_path), temp_fn=lambda: 60.0)
        assert isinstance(backend, SteamDeckFanBackend)

    def test_factory_null_without_any_chip(self, tmp_path):
        assert isinstance(select_fan_backend(None, root=str(tmp_path)), NullFanBackend)
