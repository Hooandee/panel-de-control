"""Generic AMD TDP write via the ACPI ALIB method (acpi_call). Synthetic
/proc/acpi/call via tmp_path + an injected caller for the ACPI return value."""
import os

from tdp.alib import AlibBackend
from tdp.types import TdpLimits

FALLBACK = TdpLimits(min_w=5, default_w=20, max_w=45, max_ac_w=54)


def test_default_caller_uses_shared_serialized_call(tmp_path, monkeypatch):
    """The default (non-injected) caller must go through acpi_call.serialized_call so
    the /proc/acpi/call node is shared under one lock with the fan backend."""
    import acpi_call
    p = _mk_call(str(tmp_path))
    seen = []
    monkeypatch.setattr(acpi_call, "serialized_call",
                        lambda path, cmd: seen.append((path, cmd)) or "0x0")
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=lambda m: None)
    b.set_tdp(20, ac=True)
    assert seen and seen[0][0] == p


def _mk_call(root):
    d = os.path.join(root, "proc/acpi")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "call")
    with open(path, "w") as f:
        f.write("not called")
    return path


class FakeCaller:
    """Records issued commands, returns a canned ACPI result string."""

    def __init__(self, result="0x0"):
        self.commands = []
        self._result = result

    def __call__(self, command):
        self.commands.append(command)
        return self._result


_NO_MODPROBE = lambda _m: None  # noqa: E731


def test_unsupported_when_call_interface_missing(tmp_path):
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE)
    assert b.supported is False
    res = b.set_tdp(20, ac=True)
    assert res.ok is False and res.applied_w is None  # never raises, honest failure


def test_supported_when_call_interface_writable(tmp_path):
    _mk_call(str(tmp_path))
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE)
    assert b.supported is True


def test_construction_performs_no_subprocess(tmp_path, monkeypatch):
    # Backend selection runs on the asyncio loop, so constructing must not shell
    # out. Uses the real default modprobe and asserts subprocess.run is untouched.
    import subprocess as sp
    calls = []
    monkeypatch.setattr(sp, "run", lambda *a, **k: calls.append(a))
    _mk_call(str(tmp_path))
    b = AlibBackend(FALLBACK, root=str(tmp_path))  # default (real) modprobe
    assert b.supported is True
    assert calls == []  # no subprocess on the constructing (loop) thread


def test_supported_via_module_index_and_modprobe_deferred(tmp_path):
    # No call node yet, but acpi_call is in the kernel's module index → loadable,
    # so ALIB is offered (wins over ryzenadj). The modprobe is deferred to set_tdp.
    release = os.uname().release
    mdir = tmp_path / "lib" / "modules" / release
    mdir.mkdir(parents=True)
    (mdir / "modules.dep").write_text("kernel/drivers/acpi/acpi_call.ko:\n")
    calls = []
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=lambda m: calls.append(m))
    assert b.supported is True  # loadable per module index (no node present)
    assert calls == []          # NOT loaded at construction
    res = b.set_tdp(20, ac=True)
    assert calls == ["acpi_call"]     # module load deferred to the first set_tdp
    assert res.ok is False and res.applied_w is None  # node absent → honest failure


def test_modprobe_failure_in_set_tdp_never_raises(tmp_path):
    def boom(_m):
        raise OSError("modprobe missing")

    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=boom)
    b.supported = True  # force the write path so the deferred modprobe is reached
    res = b.set_tdp(20, ac=True)  # node absent → modprobe(boom) must be swallowed
    assert res.ok is False and res.applied_w is None


def test_set_tdp_encodes_all_three_power_rails(tmp_path):
    _mk_call(str(tmp_path))
    fake = FakeCaller("0x0")
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE, caller=fake)
    res = b.set_tdp(20, ac=True)
    assert res.ok is True
    # 20 W -> 20000 mW = 0x4E20 -> little-endian bytes 20 4e 00 00.
    # Buffer = [len=0x05, cmd, val LE(4)] -> "b05" + cmd + "204e0000".
    joined = " ".join(fake.commands)
    assert "b0505204e0000" in joined  # stapm 0x05
    assert "b0506204e0000" in joined  # fast  0x06
    assert "b0507204e0000" in joined  # slow  0x07
    assert all(cmd.startswith(r"\_SB.ALIB 0x1 ") for cmd in fake.commands)
    assert len(fake.commands) == 3


def test_set_tdp_clamps_to_active_ceiling(tmp_path):
    _mk_call(str(tmp_path))
    fake = FakeCaller("0x0")
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE, caller=fake)
    res = b.set_tdp(999, ac=True)
    assert res.requested_w == 54  # clamped to max_ac
    # 54000 mW = 0xD2F0 -> LE "f0d20000".
    assert any("f0d20000" in c for c in fake.commands)


def test_set_tdp_clamps_on_battery(tmp_path):
    _mk_call(str(tmp_path))
    fake = FakeCaller("0x0")
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE, caller=fake)
    res = b.set_tdp(999, ac=False)
    assert res.requested_w == 45  # clamped to on-battery max


def test_set_tdp_reports_failure_when_method_errors(tmp_path):
    _mk_call(str(tmp_path))
    fake = FakeCaller("Error: AE_NOT_FOUND")
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE, caller=fake)
    res = b.set_tdp(20, ac=True)
    assert res.ok is False and res.applied_w is None


def test_set_tdp_does_not_claim_success_on_ambiguous_return(tmp_path):
    # The exact ALIB success code is unconfirmed on hardware, so a non-zero /
    # unparseable return is ambiguous and must NOT be reported as applied.
    _mk_call(str(tmp_path))
    for ambiguous in ("0x1", "garbage"):
        fake = FakeCaller(ambiguous)
        b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE, caller=fake)
        res = b.set_tdp(20, ac=True)
        assert res.ok is False and res.applied_w is None


def test_ensure_loaded_retries_after_transient_failure(tmp_path):
    # A first modprobe that leaves the node absent must not latch: a later set_tdp
    # retries and succeeds once the node appears (never-latch self-heal).
    calls = []
    fake = FakeCaller("0x0")

    def modprobe(_m):
        calls.append(_m)
        if len(calls) >= 2:  # node "appears" on the second attempt
            _mk_call(str(tmp_path))

    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=modprobe, caller=fake)
    b.supported = True  # force the write path so the deferred modprobe is reached
    r1 = b.set_tdp(20, ac=True)
    assert r1.ok is False and calls == ["acpi_call"]
    r2 = b.set_tdp(20, ac=True)
    assert calls == ["acpi_call", "acpi_call"]  # retried, did not latch
    assert r2.ok is True  # node present on retry → applied


def test_module_loadable_via_usrmerge_location(tmp_path):
    # usrmerge distros keep modules under /usr/lib/modules; ALIB must not be
    # falsely skipped there.
    release = os.uname().release
    mdir = tmp_path / "usr" / "lib" / "modules" / release
    mdir.mkdir(parents=True)
    (mdir / "modules.dep").write_text("kernel/drivers/acpi/acpi_call.ko:\n")
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE)
    assert b.supported is True


def test_set_tdp_reports_failure_when_call_io_fails(tmp_path):
    _mk_call(str(tmp_path))
    fake = FakeCaller(None)  # transport returned nothing
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE, caller=fake)
    res = b.set_tdp(20, ac=True)
    assert res.ok is False


def test_read_applied_is_none_write_only_interface(tmp_path):
    _mk_call(str(tmp_path))
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE)
    # ALIB does not expose the applied watts for read-back; never fabricate one.
    assert b.read_applied() is None


def test_file_caller_writes_encoded_command(tmp_path):
    # End-to-end through the real file transport: the encoded rail command reaches
    # the call node. A plain file echoes the write back (not the 0x0 status a real
    # /proc/acpi/call returns), so the write loop stops honestly after the first
    # rail — enough to prove the transport wrote the encoded command.
    path = _mk_call(str(tmp_path))
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE)
    b.set_tdp(20, ac=True)
    with open(path) as f:
        contents = f.read()
    assert "b0506204e0000" in contents  # fast rail (written first) reached the node


def test_get_limits_returns_fallback(tmp_path):
    _mk_call(str(tmp_path))
    b = AlibBackend(FALLBACK, root=str(tmp_path), modprobe=_NO_MODPROBE)
    assert b.get_limits() == FALLBACK
