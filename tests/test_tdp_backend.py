from tdp.backend import NullBackend
from tdp.types import TdpLimits


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
