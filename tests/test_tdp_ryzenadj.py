import os
from types import SimpleNamespace

from tdp import ryzenadj
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


def test_ensure_executable_adds_exec_bit(tmp_path):
    # The bundled binary can arrive mode 0o644 (a plain zip extract drops the exec
    # bit). Even root gets EACCES on a file with no exec bits set, so we self-heal.
    p = tmp_path / "ryzenadj"
    p.write_bytes(b"\x7fELF")
    os.chmod(p, 0o644)
    ryzenadj._ensure_executable(str(p))
    assert os.stat(p).st_mode & 0o111 == 0o111


def test_ensure_executable_missing_path_is_silent(tmp_path):
    # Never raises on a path that isn't there.
    ryzenadj._ensure_executable(str(tmp_path / "does-not-exist"))


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
    assert b.guard_interval_s == 15.0
    assert b.read_tolerance_w == 2
    assert b.blocking is True


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


def test_set_tdp_when_readback_unavailable_assumes_applied():
    # No STAPM limit line to read back. We can't confirm, but the write itself didn't
    # error, and this quirk doesn't mean the write failed — assume applied (unconfirmed)
    # rather than reporting a failure on a device that may well be fine.
    info = "| Name | Value | Parameter |\n| PPT FAST | 30.000 | fast-limit |\n"
    fake = FakeRun(info=info)
    b = RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=fake)
    res = b.set_tdp(20, ac=True)
    assert res.ok is True and res.applied_w is None
    assert "readback unavailable" in res.detail


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


class StickyRun:
    """Fake ryzenadj. `-i` reports the STAPM limit it currently holds. A write only
    lands once `obey_from` write attempts have happened (models amd_pmf clobbering the
    first write, then the re-assert landing); until then it holds `clobber_w` — a real,
    non-target value (a rejected/clamped write), NOT an unreadable one."""

    def __init__(self, obey_from=99, clobber_w=10):
        self.calls = []
        self._writes = 0
        self._held = clobber_w
        self._obey_from = obey_from

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if "--stapm-limit" in argv:
            self._writes += 1
            if self._writes >= self._obey_from:
                mw = argv[argv.index("--stapm-limit") + 1]
                self._held = round(int(mw) / 1000)

        held = self._held

        class R:
            returncode = 0
            stdout = f"| STAPM LIMIT | {held}.000 | stapm-limit |\n" if (
                "-i" in argv or "--info" in argv) else ""
            stderr = ""

        return R()

    @property
    def write_count(self):
        return sum(1 for c in self.calls if "--stapm-limit" in c[0])


class ScriptedRun:
    def __init__(
        self,
        *,
        write_rcs,
        infos,
        info_rcs=None,
        write_stdout="",
        write_stderr="",
    ):
        self.calls = []
        self._write_rcs = list(write_rcs)
        self._infos = list(infos)
        self._info_rcs = list(info_rcs or [0] * len(self._infos))
        self._write_stdout = write_stdout
        self._write_stderr = write_stderr

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if "-i" in argv or "--info" in argv:
            return SimpleNamespace(
                returncode=self._info_rcs.pop(0),
                stdout=self._infos.pop(0),
                stderr="",
            )
        return SimpleNamespace(
            returncode=self._write_rcs.pop(0),
            stdout=self._write_stdout,
            stderr=self._write_stderr,
        )

    @property
    def writes(self):
        return [call[0] for call in self.calls if "--stapm-limit" in call[0]]


def _stapm(watts):
    return f"| STAPM LIMIT | {watts}.000 | stapm-limit |\n"


def _unreadable_info():
    return "| Name | Value | Parameter |\n| PPT FAST | 20.000 | fast-limit |\n"


def test_non_gpd_preserves_nonzero_exit_semantics():
    fake = FakeRun(info=_unreadable_info(), rc=1)
    backend = RyzenadjBackend(
        FALLBACK,
        resolve=lambda: "/usr/bin/ryzenadj",
        runner=fake,
    )

    result = backend.set_tdp(20, ac=True)

    assert result.ok is True
    assert result.applied_w is None
    assert "readback unavailable" in result.detail
    assert sum(1 for argv, _kwargs in fake.calls if "--stapm-limit" in argv) == 2


def test_gpd_primary_success_never_uses_power_only():
    fake = ScriptedRun(write_rcs=[0], infos=[_stapm(20)])
    backend = RyzenadjBackend(
        FALLBACK,
        resolve=lambda: "/usr/bin/ryzenadj",
        runner=fake,
        power_only_retry=True,
    )

    result = backend.set_tdp(20, ac=True)

    assert result.ok is True and result.applied_w == 20
    assert len(fake.writes) == 1
    assert "--tctl-temp" in fake.writes[0]


def test_gpd_primary_zero_with_no_readback_keeps_historical_reassert():
    fake = ScriptedRun(
        write_rcs=[0, 0],
        infos=[_unreadable_info(), _unreadable_info()],
    )
    backend = RyzenadjBackend(
        FALLBACK,
        resolve=lambda: "/usr/bin/ryzenadj",
        runner=fake,
        power_only_retry=True,
    )

    result = backend.set_tdp(20, ac=True)

    assert result.ok is True and result.applied_w is None
    assert len(fake.writes) == 2
    assert all("--tctl-temp" in write for write in fake.writes)
    assert "readback unavailable" in result.detail


def test_gpd_primary_nonzero_with_confirmed_readback_succeeds_without_retry():
    fake = ScriptedRun(write_rcs=[1], infos=[_stapm(20)])
    backend = RyzenadjBackend(
        FALLBACK,
        resolve=lambda: "/usr/bin/ryzenadj",
        runner=fake,
        power_only_retry=True,
    )

    result = backend.set_tdp(20, ac=True)

    assert result.ok is True and result.applied_w == 20
    assert len(fake.writes) == 1
    assert "variant=primary" in result.detail
    assert "primary_exit=1" in result.detail
    assert "readback=confirmed" in result.detail


def test_gpd_retries_power_only_after_primary_failure():
    fake = ScriptedRun(
        write_rcs=[1, 0],
        infos=[_unreadable_info(), _stapm(20)],
    )
    backend = RyzenadjBackend(
        FALLBACK,
        resolve=lambda: "/usr/bin/ryzenadj",
        runner=fake,
        power_only_retry=True,
    )

    result = backend.set_tdp(20, ac=True)

    assert result.ok is True and result.applied_w == 20
    assert len(fake.writes) == 2
    assert "--tctl-temp" in fake.writes[0]
    assert fake.writes[1] == [
        "/usr/bin/ryzenadj",
        "--stapm-limit", "20000",
        "--fast-limit", "20000",
        "--slow-limit", "20000",
    ]
    assert "variant=power-only" in result.detail


def test_gpd_nonzero_info_exit_cannot_confirm_primary_write():
    fake = ScriptedRun(
        write_rcs=[1, 0],
        infos=[_stapm(20), _stapm(20)],
        info_rcs=[1, 0],
    )
    backend = RyzenadjBackend(
        FALLBACK,
        resolve=lambda: "/usr/bin/ryzenadj",
        runner=fake,
        power_only_retry=True,
    )

    result = backend.set_tdp(20, ac=True)

    assert result.ok is True and result.applied_w == 20
    assert len(fake.writes) == 2
    assert "variant=power-only" in result.detail


def test_gpd_power_only_success_without_readback_is_unverifiable():
    fake = ScriptedRun(
        write_rcs=[1, 0],
        infos=[_unreadable_info(), _unreadable_info()],
    )
    backend = RyzenadjBackend(
        FALLBACK,
        resolve=lambda: "/usr/bin/ryzenadj",
        runner=fake,
        power_only_retry=True,
    )

    result = backend.set_tdp(20, ac=True)

    assert result.ok is True
    assert result.applied_w is None
    assert len(fake.writes) == 2
    assert "variant=power-only" in result.detail
    assert "readback=unavailable" in result.detail


def test_gpd_power_only_nonzero_is_rejected_without_raw_output():
    fake = ScriptedRun(
        write_rcs=[1, 2],
        infos=[_unreadable_info(), _unreadable_info()],
        write_stdout="/home/private-user/device-serial",
        write_stderr="hostname=private-host",
    )
    backend = RyzenadjBackend(
        FALLBACK,
        resolve=lambda: "/usr/bin/ryzenadj",
        runner=fake,
        power_only_retry=True,
    )

    result = backend.set_tdp(20, ac=True)

    assert result.ok is False
    assert result.applied_w is None
    assert "primary_exit=1" in result.detail
    assert "exit=2" in result.detail
    assert "private-user" not in result.detail
    assert "device-serial" not in result.detail
    assert "private-host" not in result.detail


def test_gpd_power_only_nonzero_rejects_even_if_readback_matches():
    fake = ScriptedRun(
        write_rcs=[1, 2],
        infos=[_unreadable_info(), _stapm(20)],
    )
    backend = RyzenadjBackend(
        FALLBACK,
        resolve=lambda: "/usr/bin/ryzenadj",
        runner=fake,
        power_only_retry=True,
    )

    result = backend.set_tdp(20, ac=True)

    assert result.ok is False
    assert result.applied_w == 20
    assert "exit=2" in result.detail
    assert "readback=confirmed" in result.detail


def test_gpd_power_only_mismatch_reports_real_value():
    fake = ScriptedRun(
        write_rcs=[1, 0],
        infos=[_stapm(10), _stapm(12)],
    )
    backend = RyzenadjBackend(
        FALLBACK,
        resolve=lambda: "/usr/bin/ryzenadj",
        runner=fake,
        power_only_retry=True,
    )

    result = backend.set_tdp(20, ac=True)

    assert result.ok is False
    assert result.applied_w == 12
    assert "readback=mismatch" in result.detail


def test_set_tdp_not_ok_when_write_clamped_to_other_value():
    # The write is rejected/clamped and the limit holds a real, different value. Must
    # report failure with the true held value — never fake success.
    fake = StickyRun(obey_from=99, clobber_w=10)  # never obeys, always holds 10
    b = RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=fake)
    res = b.set_tdp(20, ac=True)
    assert res.ok is False
    assert res.applied_w == 10
    assert "stick" in res.detail


def test_set_tdp_reasserts_once_and_succeeds():
    # First write is clobbered, the re-assert lands. One retry is enough.
    fake = StickyRun(obey_from=2)
    b = RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=fake)
    res = b.set_tdp(20, ac=True)
    assert res.ok is True and res.applied_w == 20
    assert fake.write_count == 2  # wrote, saw it didn't stick, re-asserted once


def test_set_tdp_single_write_when_it_sticks():
    fake = StickyRun(obey_from=1)
    b = RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=fake)
    res = b.set_tdp(20, ac=True)
    assert res.ok is True and res.applied_w == 20
    assert fake.write_count == 1


def test_set_tdp_unreadable_limit_assumed_applied_not_failed():
    # Some APUs report the STAPM LIMIT line as absent or 0 even when the write applies
    # (SMU quirk). Don't cry failure on a working device: assume applied (unconfirmed),
    # report no fabricated value, and re-assert once as best effort.
    for info in ("| Name | Value |\n| PPT FAST | 20.000 | fast-limit |\n",   # no STAPM line
                 "| STAPM LIMIT | 0.000 | stapm-limit |\n"):                  # reads zero
        fake = FakeRun(info=info)
        b = RyzenadjBackend(FALLBACK, resolve=lambda: "/usr/bin/ryzenadj", runner=fake)
        res = b.set_tdp(20, ac=True)
        assert res.ok is True
        assert res.applied_w is None
        assert "readback unavailable" in res.detail
        assert sum(1 for c in fake.calls if "--stapm-limit" in c[0]) == 2  # re-asserted
