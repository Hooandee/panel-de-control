"""A fresh install starts from the power the machine already runs, so installing Panel
changes nothing until the user moves the dial."""
import importlib
import sys
import types

import pytest

from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult


class ReadableBackend:
    supported = True
    supports_levels = True
    name = "firmware-attr:lenovo-wmi-other"
    unit = "W"
    readback = True
    primary_rail = "pl1"
    seeds_from_readback = True

    def __init__(self, rails):
        self.rails = dict(rails)
        self.writes = []

    def get_limits(self):
        return TdpLimits(min_w=5, default_w=15, max_w=33, max_ac_w=40)

    def level_limits(self):
        return {"pl1": {"min": 5, "max": 33}, "pl2": {"min": 5, "max": 33},
                "pl3": {"min": 5, "max": 35}}

    def observe(self):
        return TdpObservation(
            readable=True,
            surfaces={self.name: {rail: RailReading(value) for rail, value in self.rails.items()}},
        )

    def set_levels(self, pl1, pl2, pl3, ac):
        self.writes.append((pl1, pl2, pl3))
        return TdpResult(pl1, pl1, True, "")

    def read_applied(self):
        return self.rails.get(self.primary_rail)

    def release(self):
        return True


class FakeFan:
    supported = True
    name = "fake-fan"

    def read_state(self):
        return {"supported": True, "source": "fake", "pwm_max": 255, "fans": []}

    def apply_curve_all(self, points):
        pass

    def set_auto(self, points):
        pass

    def restore_auto(self):
        pass


@pytest.fixture
def make_plugin(tmp_path, monkeypatch):
    def build(rails, *, on_ac=False, battery=80, backend_cls=ReadableBackend):
        fake = types.ModuleType("decky")
        fake.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
        fake.DECKY_USER = "deck"
        fake.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                            warning=lambda *a, **k: None,
                                            error=lambda *a, **k: None)
        monkeypatch.setitem(sys.modules, "decky", fake)
        backend = backend_cls(rails)
        import tdp.factory as factory
        monkeypatch.setattr(factory, "select_backend", lambda device, **kw: backend)
        import fans.control as fan_control
        monkeypatch.setattr(fan_control, "select_fan_backend", lambda device, **kw: FakeFan())
        import lifecycle
        monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": on_ac)
        main = importlib.reload(importlib.import_module("main"))
        monkeypatch.setattr(main, "read_on_ac", lambda root="/": on_ac, raising=False)
        plugin = main.Plugin()
        plugin._init()
        plugin._tdp_backend = backend
        plugin._battery = types.SimpleNamespace(read=lambda: {"percent": battery})
        return plugin, backend
    return build


def _rails(plugin):
    eff = plugin._tdp_profiles.effective(None)
    return eff["pl1"], eff["pl2"], eff["pl3"], eff["mode"]


def test_fresh_install_adopts_steamos_flat_power(make_plugin):
    plugin, _ = make_plugin({"pl1": 33, "pl2": 33, "pl3": 33})
    plugin._seed_tdp_from_hardware()
    assert _rails(plugin) == (33, 33, 33, "estable")
    assert plugin._tdp_profiles.seed_pending is False


def test_fresh_install_keeps_firmware_boost_within_rail_limits(make_plugin):
    plugin, _ = make_plugin({"pl1": 22, "pl2": 18, "pl3": 37})
    plugin._seed_tdp_from_hardware()
    assert _rails(plugin) == (22, 22, 35, "custom")


def test_seed_waits_on_low_battery_where_firmware_caps_power(make_plugin):
    plugin, _ = make_plugin({"pl1": 15, "pl2": 15, "pl3": 20}, battery=18)
    before = _rails(plugin)
    plugin._seed_tdp_from_hardware()
    assert plugin._tdp_profiles.seed_pending is True
    assert _rails(plugin) == before


def test_seed_waits_for_battery_because_charger_power_is_not_the_battery_profile(make_plugin):
    plugin, _ = make_plugin({"pl1": 38, "pl2": 38, "pl3": 38}, on_ac=True)
    before = _rails(plugin)
    plugin._seed_tdp_from_hardware()
    assert _rails(plugin) == before
    assert plugin._tdp_profiles.seed_pending is True


def test_seed_waits_while_the_firmware_keeps_its_low_battery_cap_until_reboot(make_plugin, monkeypatch):
    import main
    plugin, _ = make_plugin({"pl1": 15, "pl2": 15, "pl3": 20}, battery=60)
    monkeypatch.setattr(main, "_current_boot_id", lambda: "boot-1")
    plugin._settings["low_battery_hold_latched_boot"] = "boot-1"
    before = _rails(plugin)
    plugin._seed_tdp_from_hardware()
    assert _rails(plugin) == before
    assert plugin._tdp_profiles.seed_pending is True


def test_unvalidated_route_keeps_the_previous_default(make_plugin):
    class Unvalidated(ReadableBackend):
        seeds_from_readback = False

    plugin, _ = make_plugin({"pl1": 30, "pl2": 30, "pl3": 30}, backend_cls=Unvalidated)
    before = _rails(plugin)
    plugin._seed_tdp_from_hardware()
    assert _rails(plugin) == before


def test_seed_uses_primary_rail_when_backend_has_no_pl1(make_plugin):
    class DeckLike(ReadableBackend):
        name = "steamdeck-hwmon"
        primary_rail = "pl2"

        def level_limits(self):
            return {"pl2": {"min": 3, "max": 15}, "pl3": {"min": 3, "max": 15}}

        def get_limits(self):
            return TdpLimits(min_w=3, default_w=12, max_w=15, max_ac_w=15)

    plugin, _ = make_plugin({"pl2": 15, "pl3": 15}, backend_cls=DeckLike)
    plugin._seed_tdp_from_hardware()
    assert _rails(plugin)[:3] == (15, 15, 15)


def test_seed_skips_backends_without_readback(make_plugin):
    class Blind(ReadableBackend):
        readback = False

    plugin, _ = make_plugin({"pl1": 30}, backend_cls=Blind)
    before = _rails(plugin)
    plugin._seed_tdp_from_hardware()
    assert plugin._tdp_profiles.seed_pending is True
    assert _rails(plugin) == before


def test_seed_never_overrides_a_user_choice(make_plugin):
    plugin, _ = make_plugin({"pl1": 33, "pl2": 33, "pl3": 33})
    plugin._tdp_profiles.set_pl1("global", 9)
    plugin._seed_tdp_from_hardware()
    assert _rails(plugin)[0] == 9


def test_seed_does_not_write_hardware(make_plugin):
    plugin, backend = make_plugin({"pl1": 33, "pl2": 33, "pl3": 33})
    plugin._seed_tdp_from_hardware()
    assert backend.writes == []


@pytest.mark.parametrize("broken", ["observe", "level_limits"])
def test_unreadable_hardware_leaves_the_default_and_never_breaks_startup(make_plugin, broken):
    def fail(self, *args):
        raise OSError("sysfs vanished")

    Broken = type("Broken", (ReadableBackend,), {broken: fail})

    plugin, _ = make_plugin({"pl1": 33}, backend_cls=Broken)
    before = _rails(plugin)
    plugin._seed_tdp_from_hardware()
    assert _rails(plugin) == before
    assert plugin._tdp_profiles.seed_pending is True
