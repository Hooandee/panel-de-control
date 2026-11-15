import ast
import importlib
import pathlib
import sys
import types

from tdp.backend import TDPBackend
from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult


def fake_decky(monkeypatch, settings_dir, user="deck"):
    """Install a fake ``decky`` module and return the log calls it records."""
    fake = types.ModuleType("decky")
    fake.DECKY_PLUGIN_SETTINGS_DIR = str(settings_dir)
    fake.DECKY_USER = user
    logs = {"info": [], "warning": [], "error": [], "exception": [], "debug": []}
    fake.logger = types.SimpleNamespace(
        **{level: (lambda calls: lambda *a, **k: calls.append(a))(calls) for level, calls in logs.items()}
    )
    monkeypatch.setitem(sys.modules, "decky", fake)
    return logs


def _main_bindings():
    path = pathlib.Path(__file__).resolve().parents[1] / "main.py"
    bindings = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            bindings += [(a.asname or a.name, node.module, a.name) for a in node.names]
        elif isinstance(node, ast.Import):
            bindings += [(a.asname or a.name, a.name, None) for a in node.names if a.asname or "." not in a.name]
    return bindings


_MAIN_BINDINGS = []


def load_main(monkeypatch):
    """Return ``main`` rebound to the modules currently in ``sys.modules``.

    Same effect as ``importlib.reload(main)`` for everything the plugin imports
    (including names patched on their source module), without re-executing main.py.
    """
    main = importlib.import_module("main")
    if not _MAIN_BINDINGS:
        _MAIN_BINDINGS.extend(_main_bindings())
    for name, module, attr in _MAIN_BINDINGS:
        source = sys.modules.get(module)
        if source is None:
            continue
        value = source if attr is None else getattr(source, attr)
        if getattr(main, name, None) is not value:
            monkeypatch.setattr(main, name, value, raising=False)
    return main


class FakeBackend(TDPBackend):
    supported = True
    supports_levels = True
    auto_tdp_safe = True
    name = "fake"
    low_battery_hold_strategy = "primary"

    def __init__(self):
        self.set_levels_calls = 0
        self.live_max = 35
        self._levels = {"pl1": 15, "pl2": 15, "pl3": 15}
        self._legacy_levels = None
        self._profile = "custom"

    def get_limits(self):
        return TdpLimits(min_w=5, default_w=15, max_w=35, max_ac_w=35)

    def level_limits(self):
        return {
            "pl1": {"min": 5, "max": 35},
            "pl2": {"min": 5, "max": 42},
            "pl3": {"min": 5, "max": 49},
        }

    def set_tdp(self, watts, ac):
        return self.set_levels(watts, watts, watts, ac)

    def set_levels(self, pl1, pl2, pl3, ac):
        self.set_levels_calls += 1
        self._levels = {
            "pl1": min(int(pl1), self.live_max),
            "pl2": int(pl2),
            "pl3": int(pl3),
        }
        if self._legacy_levels is not None:
            self._legacy_levels = dict(self._levels)
        return TdpResult(pl1, self._levels["pl1"], True, "")

    def read_applied(self):
        return self._levels["pl1"]

    def observe(self):
        surfaces = {
            self.name: {
                "pl1": RailReading(
                    self._levels["pl1"],
                    5,
                    self.live_max,
                ),
                "pl2": RailReading(self._levels["pl2"], 15, 42),
                "pl3": RailReading(self._levels["pl3"], 15, 49),
            },
        }
        if self._legacy_levels is not None:
            surfaces["legacy"] = {
                rail: RailReading(value)
                for rail, value in self._legacy_levels.items()
            }
        return TdpObservation(
            readable=True,
            surfaces=surfaces,
        )

    def set_surface(self, surface, **levels):
        if surface == "armoury":
            self._levels.update(levels)
        elif surface == "legacy":
            if self._legacy_levels is None:
                self._legacy_levels = dict(self._levels)
            self._legacy_levels.update(levels)

    def surface(self, surface):
        levels = (
            self._levels
            if surface == "armoury"
            else self._legacy_levels
        )
        return dict(levels) if levels is not None else None

    def profile_choices(self):
        return ["low-power", "balanced", "performance", "custom"]

    def set_profile(self, mode):
        self._profile = mode
        return True


class FakeFan:
    supported = True
    name = "fake-fan"

    def read_state(self):
        return {
            "supported": True,
            "source": "fake",
            "pwm_max": 255,
            "fans": [],
        }

    def apply_curve_all(self, points):
        pass

    def set_auto(self, points):
        pass

    def restore_auto(self):
        pass


class FakeLowBatteryHoldBackend:
    supported = True
    low_battery_hold_capable = True
    low_battery_hold_strategy = "legion-go-s-83n6"
    name = "ryzenadj-low-battery-hold"
    safety_locked = False

    def __init__(self):
        self.calls = []
        self.active = False
        self.releases = 0
        self.release_ok = True

    def low_battery_level_limits(self, maximum=None):
        maximum = 35 if maximum is None else int(maximum)
        return {
            "pl1": {"min": 5, "max": maximum},
            "pl2": {"min": 15, "max": maximum},
            "pl3": {"min": 20, "max": maximum},
        }

    def hold_levels(self, levels):
        self.calls.append(dict(levels))
        self.active = True
        self.safety_locked = True
        return TdpResult(
            levels["pl1"],
            None,
            True,
            "command accepted (limit readback unavailable)",
        )

    def release_hold(self):
        self.releases += 1
        if not self.release_ok:
            return False
        self.active = False
        self.safety_locked = False
        return True

    def observe_hold(self):
        return TdpObservation(readable=False)

    def diagnostics(self):
        return {"low_battery_hold_active": self.active}
