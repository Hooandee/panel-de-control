from tdp.backend import NullBackend, TDPBackend
from tdp.types import TdpLimits, TdpResult


def test_null_backend_unsupported():
    b = NullBackend("no supported TDP interface found")
    assert b.supported is False
    res = b.set_tdp(15, ac=True)
    assert res.ok is False
    assert res.requested_w == 15
    assert "unsupported" in res.detail.lower()
    assert b.read_applied() is None


def test_null_backend_limits_are_zero():
    b = NullBackend("x")
    lim = b.get_limits()
    assert isinstance(lim, TdpLimits)
    assert lim.max_ac_w == 0


def test_base_observe_adapts_legacy_pl1_readback():
    class Readable(NullBackend):
        supported = True
        name = "readable"
        readback = True

        def read_applied(self):
            return 17

    obs = Readable("x").observe()
    assert obs.readable is True
    assert obs.surfaces["readable"]["pl1"].applied_w == 17


def test_backend_guard_defaults_are_cheap_readback():
    assert TDPBackend.readback is True
    assert TDPBackend.guard_interval_s == 2.0
    assert TDPBackend.heartbeat_s is None
    assert TDPBackend.read_tolerance_w == 0


def test_single_rail_backend_only_reconciles_pl1():
    b = NullBackend("x")
    assert b.reconciliation_levels(
        {"pl1": 15, "pl2": 20, "pl3": 25}
    ) == {"pl1": 15}


def test_multi_rail_backend_reconciles_all_levels():
    class Multi(NullBackend):
        supports_levels = True

    b = Multi("x")
    assert b.reconciliation_levels(
        {"pl1": 15, "pl2": 20, "pl3": 25}
    ) == {"pl1": 15, "pl2": 20, "pl3": 25}


def test_legacy_backend_physical_contract_preserves_all_existing_rails():
    class Multi(TDPBackend):
        supports_levels = True

        def get_limits(self):
            return TdpLimits(5, 15, 20, 30)

        def set_tdp(self, watts, ac):
            return TdpResult(watts, watts, True, "")

        def read_applied(self):
            return 15

        def set_levels(self, pl1, pl2, pl3, ac):
            self.applied = (pl1, pl2, pl3, ac)
            return TdpResult(pl1, pl1, True, "")

    backend = Multi()
    levels = {"pl1": 15, "pl2": 20, "pl3": 25}

    assert backend.primary_rail == "pl1"
    assert backend.physical_levels(levels) == levels
    result = backend.apply_targets(levels, True)
    assert result.ok is True
    assert backend.applied == (15, 20, 25, True)
