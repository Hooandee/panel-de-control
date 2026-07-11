from tdp.ryzenadj import RyzenadjBackend
from tdp.types import TdpLimits

FALLBACK = TdpLimits(min_w=5, default_w=15, max_w=25, max_ac_w=30)

INFO_OUTPUT = """\
| Name                | Value    | Parameter        |
| STAPM LIMIT         |   15.000 | stapm-limit      |
| STAPM VALUE         |    3.500 |                  |
| PPT LIMIT FAST      |   15.000 | fast-limit       |
"""


class FakeRun:
    def __init__(self, info=INFO_OUTPUT, rc=0):
        self.calls = []
        self._info = info
        self._rc = rc

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))

        class R:
            returncode = self._rc
            stdout = self._info if "-i" in argv or "--info" in argv else ""
            stderr = ""

        return R()


def test_unsupported_when_binary_missing():
    b = RyzenadjBackend(FALLBACK, resolve=lambda: None)
    assert b.supported is False
    assert b.set_tdp(15, ac=True).ok is False


def test_set_tdp_sends_milliwatts_to_all_three_limits():
    fake = FakeRun()
    b = RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=fake)
    b.set_tdp(15, ac=True)
    set_call = next(c for c in fake.calls if "--stapm-limit" in c[0])
    argv = set_call[0]
    assert "15000" in argv  # milliwatts
    assert "--stapm-limit" in argv and "--fast-limit" in argv and "--slow-limit" in argv
    # LD_LIBRARY_PATH cleared in env
    env = set_call[1].get("env", {})
    assert env.get("LD_LIBRARY_PATH", "") == ""


def test_read_applied_parses_watts_from_info():
    fake = FakeRun()
    b = RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=fake)
    assert b.read_applied() == 15


def test_set_tdp_clamps():
    fake = FakeRun(info=INFO_OUTPUT.replace("15.000", "25.000"))
    b = RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=fake)
    res = b.set_tdp(99, ac=True)
    # requested clamped to 30 (max_ac); applied read back from (faked) info
    assert res.requested_w == 99


def test_read_applied_none_when_stapm_absent():
    # No stapm/sustained rail in the output — report unreadable, never guess
    # from another rail.
    info = "| Name | Value | Parameter |\n| PPT FAST | 30.000 | fast-limit |\n"
    fake = FakeRun(info=info)
    b = RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=fake)
    assert b.read_applied() is None


def test_set_tdp_not_ok_when_readback_unavailable():
    info = "| Name | Value | Parameter |\n| PPT FAST | 30.000 | fast-limit |\n"
    fake = FakeRun(info=info)
    b = RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=fake)
    res = b.set_tdp(20, ac=True)
    assert res.ok is False and res.applied_w is None


def test_write_max_widens_the_write_clamp():
    base = FakeRun()
    RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=base).set_tdp(70, ac=True)
    argv = next(c for c in base.calls if "--stapm-limit" in c[0])[0]
    assert "30000" in argv
    boosted = FakeRun()
    b = RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=boosted, write_max=75)
    b.set_tdp(70, ac=True)
    argv = next(c for c in boosted.calls if "--stapm-limit" in c[0])[0]
    assert "70000" in argv
    assert b.get_limits().max_ac_w == 30
