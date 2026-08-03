"""RPC-level tests for CPU controls (get_cpu_state, set_smt, set_cpu_boost).

Same Plugin bootstrap as test_battery_rpc: fake decky + fake TDP backend so _init
never touches live hardware, then inject fake SMT/boost controls.
"""
import asyncio
import importlib
import sys
import types

from cpu.frequency import CpuFrequencyResult


class _FakeToggle:
    def __init__(self, supported=True, on=True):
        self.supported = supported
        self._on = on

    def enabled(self):
        return self._on if self.supported else False

    def set(self, enabled):
        if not self.supported:
            return False
        self._on = bool(enabled)
        return True


class _FakeCores:
    def __init__(self, supported=True, max_cores=8, active=8):
        self.supported = supported
        self.max_cores = max_cores if supported else None
        self._active = active

    def active(self):
        return self._active

    def set(self, n):
        self._active = max(1, min(self.max_cores, int(n)))
        return True


class _FakeFrequency:
    def __init__(self, supported=True, ok=True, status="applied"):
        self.supported = supported
        self.ok = ok
        self.status = status
        self.calls = []
        self.window = (400_000, 3_500_000)
        self.requested = None

    def get_range(self):
        return self.window if self.supported else None

    def set_window(self, minimum, maximum):
        self.calls.append(("manual", minimum, maximum))
        if self.ok:
            self.requested = (minimum, maximum)
        return CpuFrequencyResult(
            self.ok, self.status, (minimum, maximum),
            self.requested or self.window,
            {"attempted": not self.ok, "ok": True if not self.ok else None},
            None if self.ok else "write_failed", 0,
        )

    def set_auto(self):
        self.calls.append(("auto",))
        self.requested = None
        return CpuFrequencyResult(
            True, "restored", None, self.window,
            {"attempted": True, "ok": True}, None, 0,
        )

    def diagnostics(self):
        minimum, maximum = self.requested or self.window
        return {
            "supported": self.supported,
            "backend": "fake_cpufreq" if self.supported else "unsupported",
            "reason": None,
            "epoch": 0,
            "requested": list(self.requested) if self.requested else None,
            "owned": self.requested is not None,
            "policies": ["policy0"] if self.supported else [],
            "drivers": ["fake"] if self.supported else [],
            "policy_state": ([{
                "name": "policy0",
                "cpus": [0, 1, 2, 3],
                "driver": "fake",
                "hardware_min_khz": 400_000,
                "hardware_max_khz": 3_500_000,
                "applied_min_khz": minimum,
                "applied_max_khz": maximum,
            }] if self.supported else []),
        }


def _make_plugin(tmp_path, monkeypatch, smt=None, boost=None, cores=None, frequency=None):
    fake_decky = types.ModuleType("decky")
    fake_decky.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake_decky.DECKY_USER = "deck"
    fake_decky.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    monkeypatch.setitem(sys.modules, "decky", fake_decky)

    import tdp.factory as factory
    from tdp.types import TdpLimits, TdpResult

    class _FakeBackend:
        supported = True
        supports_levels = False
        name = "fake"

        def get_limits(self):
            return TdpLimits(min_w=5, default_w=15, max_w=20, max_ac_w=60)

        def level_limits(self):
            return {}

        def set_tdp(self, w, ac):
            return TdpResult(w, w, True, "")

        def set_levels(self, pl1, pl2, pl3, ac):
            return TdpResult(pl1, pl1, True, "")

        def read_applied(self):
            return 15

    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: _FakeBackend())

    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)

    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    if frequency is not None:
        monkeypatch.setattr(main, "select_cpu_frequency", lambda: frequency)

    if smt is not None or boost is not None or cores is not None:
        original_init = main.Plugin._init

        def patched_init(self):
            original_init(self)
            if smt is not None:
                self._smt = smt
            if boost is not None:
                self._boost = boost
            if cores is not None:
                self._cores = cores
            self._cpu_coordinator = main.CpuCoordinator(
                self._cores, self._smt, self._boost, self._cpu_frequency
            )

        monkeypatch.setattr(main.Plugin, "_init", patched_init)

    return main.Plugin()


def test_get_cpu_state_shape(tmp_path, monkeypatch):
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        frequency=_FakeFrequency(),
    )
    st = asyncio.run(p.get_cpu_state())
    assert "chip" in st
    assert st["smt"] == {"supported": True, "enabled": True}
    assert st["boost"] == {"supported": True, "enabled": True}
    assert "cores" in st and "max_khz" in st
    assert st["frequency"]["supported"] is True
    assert st["frequency"]["range_min_khz"] == 400_000
    assert st["frequency"]["policy_state"][0]["name"] == "policy0"


def test_set_smt_toggles_and_persists(tmp_path, monkeypatch):
    smt = _FakeToggle(on=True)
    p = _make_plugin(tmp_path, monkeypatch, smt=smt, boost=_FakeToggle())
    st = asyncio.run(p.set_smt(False))
    assert smt.enabled() is False
    assert st["smt"]["enabled"] is False
    # persisted
    p2 = _make_plugin(tmp_path, monkeypatch, smt=_FakeToggle(on=True), boost=_FakeToggle())
    p2._init()
    p2._apply_cpu()  # startup re-applies persisted state
    assert p2._smt.enabled() is False


def test_set_boost_toggles(tmp_path, monkeypatch):
    boost = _FakeToggle(on=True)
    p = _make_plugin(tmp_path, monkeypatch, smt=_FakeToggle(), boost=boost)
    asyncio.run(p.set_cpu_boost(False))
    assert boost.enabled() is False


def test_set_active_cores_persists_and_reapplies(tmp_path, monkeypatch):
    cores = _FakeCores(max_cores=8, active=8)
    p = _make_plugin(tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(), cores=cores)
    st = asyncio.run(p.set_active_cores(4))
    assert cores.active() == 4
    assert st["active_cores"] == 4 and st["max_cores"] == 8 and st["cores_supported"] is True
    # persisted → startup re-applies
    p2 = _make_plugin(tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
                      cores=_FakeCores(max_cores=8, active=8))
    p2._init()
    p2._apply_cpu()
    assert p2._cores.active() == 4


def test_cores_unsupported_hides(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
                     cores=_FakeCores(supported=False))
    st = asyncio.run(p.get_cpu_state())
    assert st["cores_supported"] is False and st["active_cores"] is None


def test_unsupported_controls_degrade(tmp_path, monkeypatch):
    p = _make_plugin(
        tmp_path, monkeypatch,
        smt=_FakeToggle(supported=False), boost=_FakeToggle(supported=False),
    )
    st = asyncio.run(p.set_smt(False))
    assert st["smt"]["supported"] is False
    st2 = asyncio.run(p.set_cpu_boost(False))
    assert st2["boost"]["supported"] is False


def test_set_cpu_frequency_applies_before_persisting_profile(tmp_path, monkeypatch):
    frequency = _FakeFrequency()
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        frequency=frequency,
    )

    state = asyncio.run(p.set_cpu_frequency(1_200_000, 2_400_000))

    assert frequency.calls[-1] == ("manual", 1_200_000, 2_400_000)
    assert p._cpu_profiles.effective(None)["frequency"] == {
        "manual": True, "min_khz": 1_200_000, "max_khz": 2_400_000,
    }
    assert state["frequency"]["status"] == "applied"
    assert state["frequency"]["applied_min_khz"] == 1_200_000


def test_rejected_cpu_frequency_does_not_replace_profile(tmp_path, monkeypatch):
    frequency = _FakeFrequency(ok=False, status="failed")
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        frequency=frequency,
    )
    p._init()
    before = p._cpu_profiles.effective(None)["frequency"]

    state = asyncio.run(p.set_cpu_frequency(1_200_000, 2_400_000))

    assert p._cpu_profiles.effective(None)["frequency"] == before
    assert state["frequency"]["status"] == "failed"
    assert state["frequency"]["reason"] == "frequency_write_failed"


def test_set_cpu_frequency_auto_restores_then_persists_auto(tmp_path, monkeypatch):
    frequency = _FakeFrequency()
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        frequency=frequency,
    )
    assert asyncio.run(p.set_cpu_frequency(1_200_000, 2_400_000))["frequency"]["manual"] is True

    state = asyncio.run(p.set_cpu_frequency_auto())

    assert frequency.calls[-1] == ("auto",)
    assert p._cpu_profiles.effective(None)["frequency"] == {
        "manual": False, "min_khz": None, "max_khz": None,
    }
    assert state["frequency"]["manual"] is False


def test_cpu_frequency_apply_uses_offload_chokepoint(tmp_path, monkeypatch):
    frequency = _FakeFrequency()
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        frequency=frequency,
    )
    calls = []

    async def recording_offload(fn):
        calls.append("offload")
        return fn()

    p._offload_call = recording_offload
    asyncio.run(p.set_cpu_frequency(1_200_000, 2_400_000))

    assert calls == ["offload"]
