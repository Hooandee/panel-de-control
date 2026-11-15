import pytest
from tdp.types import TdpLimits, TdpResult
from main_harness import fake_decky, load_main


@pytest.fixture
def Plugin(tmp_path, monkeypatch):
    fake_decky(monkeypatch, tmp_path)
    import tdp.factory as factory
    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: FakeBackend())
    import fans.control as fan_control
    monkeypatch.setattr(fan_control, "select_fan_backend", lambda device, **kw: FakeFan())
    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = load_main(monkeypatch)
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    return main.Plugin


class FakeBackend:
    supported = True
    supports_levels = True
    name = "fake"

    def __init__(self):
        self.set_levels_calls = 0
        self.release_calls = 0
        self.release_ok = True
        self._applied = None

    def get_limits(self):
        return TdpLimits(min_w=5, default_w=15, max_w=35, max_ac_w=35)

    def level_limits(self):
        return {"pl1": {"min": 5, "max": 35}}

    def set_levels(self, pl1, pl2, pl3, ac):
        self.set_levels_calls += 1
        self._applied = pl1
        return TdpResult(pl1, pl1, True, "")

    def read_applied(self):
        return self._applied

    def release(self):
        self.release_calls += 1
        return self.release_ok


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
