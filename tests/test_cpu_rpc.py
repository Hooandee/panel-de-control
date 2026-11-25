"""RPC-level tests for CPU controls (get_cpu_state, set_smt, set_cpu_boost).

Same Plugin bootstrap as test_battery_rpc: fake decky + fake TDP backend so _init
never touches live hardware, then inject fake SMT/boost controls.
"""
import asyncio
import importlib
import json
import sys
import types
from functools import partial

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


class _FailingToggle(_FakeToggle):
    def set(self, enabled):
        return False


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


def _make_plugin(tmp_path, monkeypatch, smt=None, boost=None, cores=None, frequency=None,
                 *, fake_tdp=True):
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

    if fake_tdp:
        monkeypatch.setattr(factory, "select_backend", lambda device, **kw: _FakeBackend())

    import lifecycle
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)

    main = importlib.reload(importlib.import_module("main"))
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    if frequency is not None:
        monkeypatch.setattr(
            main, "select_cpu_frequency", lambda **_kwargs: frequency
        )

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


def test_flip_ds_lifecycle_requires_opt_in_and_restores_tdp(tmp_path, monkeypatch):
    root = str(tmp_path)
    files = {
        "class/dmi/id/sys_vendor": "AYANEO",
        "class/dmi/id/product_name": "FLIP 1S DS",
        "class/power_supply/ACAD/type": "Mains",
        "class/power_supply/ACAD/online": "0",
        "class/hwmon/hwmon7/name": "ayaneo_ec",
        "class/hwmon/hwmon7/fan1_input": "3599",
        "class/hwmon/hwmon7/pwm1_enable": "2",
        "devices/system/cpu/cpu2/online": "0",
        "devices/system/cpu/smt/control": "off",
        "devices/system/cpu/cpufreq/boost": "0",
    }
    for name, value in files.items():
        path = tmp_path / "sys" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    (tmp_path / "state.json").write_text(json.dumps({
        "tdp_control_enabled": True, "hhd_tdp_takeover": True, "hhd_tdp_prev": True,
        "auto_tdp": True, "low_battery_tdp_hold": True,
        "gpu_handoff_pending": True, "fan_release_pending": True,
        "desktop_mode_enabled": True, "desktop_power_mode": "performance",
    }))
    (tmp_path / "tdp_profiles.json").write_text(json.dumps({
        "global": {"watts": 15, "auto_tdp": True},
    }))

    plugin = _make_plugin(tmp_path, monkeypatch, fake_tdp=False)
    import main

    monkeypatch.setattr(main, "read_on_ac", lambda: False)
    original_limits = (28125, 54875, 45375)
    limits = original_limits
    rail_writes = []

    def run_ryzenadj(argv, **kwargs):
        nonlocal limits
        if argv[1:] == ["-i"]:
            stdout = "\n".join(
                f"{name} | {value / 1000:.3f} |"
                for name, value in zip(
                    ("STAPM LIMIT", "PPT LIMIT FAST", "PPT LIMIT SLOW"), limits
                )
            )
            return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        assert argv[1::2] == ["--stapm-limit", "--fast-limit", "--slow-limit"]
        limits = tuple(map(int, argv[2::2]))
        assert limits == original_limits or all(0 < value <= 25000 for value in limits)
        rail_writes.append(limits)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        main.tdp_factory, "RyzenadjBackend",
        partial(main.tdp_factory.RyzenadjBackend, runner=run_ryzenadj),
    )
    monkeypatch.setattr(
        main.tdp_factory, "select_backend",
        partial(main.tdp_factory.select_backend, root=root, ryzenadj_resolve=lambda: "ryzenadj"),
    )
    conflict = True
    monkeypatch.setattr(
        main.powerstation_conflict.Detector, "tdp_active", lambda self: conflict,
    )
    detect = main.device_registry.detect
    monkeypatch.setattr(main.device_registry, "detect", partial(detect, root=root))
    for name in ("CoreControl", "SmtControl", "select_boost", "FanReader"):
        monkeypatch.setattr(main, name, partial(getattr(main, name), root=root))
    select_fan = main.fan_control.select_fan_backend
    monkeypatch.setattr(main.fan_control, "select_fan_backend", partial(select_fan, root=root))
    monkeypatch.setattr(main.Plugin, "_start_steam_inventory_compat", lambda self: None)
    monkeypatch.setattr(main.osinfo, "read_os_id", lambda: "cachyos")

    writes = []

    def reject_write(*args, **kwargs):
        writes.append((args, kwargs))
        raise AssertionError("unexpected power or fan write")

    monkeypatch.setattr(main.CpuCoordinator, "apply", reject_write)
    monkeypatch.setattr(main.fan_expose, "ensure_fan_sensor", reject_write)
    monkeypatch.setattr(main.controller_hhd, "set_tdp_enable", reject_write)

    async def exercise():
        nonlocal conflict
        await plugin._main()
        try:
            assert (await plugin.get_device())["key"] == "ayaneo_flip_1s_ds"
            plugin._reapply_all(on_ac=False)
            await plugin._drain_offloaded()
            fan = await plugin.get_fan_state()
            assert [(item["rpm"], item["percent"]) for item in fan["fans"]] == [(3599, None)]
            assert not (await plugin.set_smt(True))["smt"]["supported"]
            assert not (await plugin.set_gpu_clock(600, 1200))["supported"]
            assert not (await plugin.set_fan_preset("balanced", "global"))["supported"]
            assert not await plugin.get_tdp_control_enabled()
            assert "power" in (await plugin.set_ui_module("power", False))["disabled"]
            assert rail_writes == []

            conflict = False
            assert "power" not in (await plugin.set_ui_module("power", False))["disabled"]
            assert await plugin.get_tdp_control_enabled()
            state = await plugin.get_tdp_state()
            assert state["supports_auto_tdp"]
            assert not state["auto_config"]["enabled"]
            assert state["low_battery_hold"]["available"]
            assert not state["low_battery_hold"]["enabled"]

            assert (await plugin.set_auto_tdp(True))["auto_tdp"]
            assert (await plugin.get_tdp_state())["auto_config"]["enabled"]
            assert not (await plugin.set_auto_tdp(False))["auto_tdp"]

            monkeypatch.setattr(plugin._battery, "read", lambda: {
                "present": True, "percent": 20, "status": "Discharging",
            })
            assert (await plugin.set_tdp_watts(25, "global"))["ok"]
            assert limits == (25000, 25000, 25000)
            hold = (await plugin.set_low_battery_tdp_hold(True))["low_battery_hold"]
            assert hold["enabled"] and hold["active"] and hold["verified"]
            conflict = True
            write_count = len(rail_writes)
            await plugin._offload_call(plugin._tdp_guard_tick)
            hold = (await plugin.get_tdp_state())["low_battery_hold"]
            assert not hold["active"] and hold["reason"] == "external_owner"
            assert len(rail_writes) == write_count
            conflict = False
            write_count = len(rail_writes)
            for setter in (plugin.set_tdp_watts, plugin.apply_power_preset):
                result = await setter(26, "global")
                assert not result["ok"]
                assert result["detail"] == "tdp-request-exceeds-25w-ceiling"
            assert len(rail_writes) == write_count
        finally:
            await plugin._unload()

    asyncio.run(exercise())
    assert limits == original_limits
    assert rail_writes[-1] == original_limits
    assert not (tmp_path / "run/panel-de-control/ryzenadj-ayaneo_flip_1s_ds.lock").exists()
    assert writes == []
    for name, value in files.items():
        assert (tmp_path / "sys" / name).read_text() == value


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


def test_cpu_report_retains_failure_readback_without_private_backend_data(
    tmp_path, monkeypatch
):
    from cpu.coordinator import CpuCoordinatorResult

    frequency = _FakeFrequency()
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        frequency=frequency,
    )
    p._init()
    failure = {
        "reason": "readback_mismatch",
        "requested": [419_175, 4_000_000],
        "policies": [{
            "name": "policy0",
            "driver": "amd-pstate-epp",
            "hardware_bounds": [419_175, 5_134_889],
            "target": [419_175, 4_000_000],
            "applied": [419_175, 3_301_000],
            "identity_changed_fields": [],
            "path": "/home/private-user/sysfs/policy0",
        }],
        "policies_omitted": 0,
        "raw_output": "/home/private-user/game",
    }
    original_diagnostics = frequency.diagnostics
    monkeypatch.setattr(
        frequency, "diagnostics",
        lambda: {**original_diagnostics(), "last_failure": failure},
    )
    p._cpu_generation = 7
    p._record_cpu_result(CpuCoordinatorResult(
        False, "failed", 7, {"attempted": True, "ok": True},
        "frequency_readback_mismatch",
    ), "set_frequency")

    frequency.window = (419_175, 5_134_889)
    failure["policies"][0]["applied"] = [419_175, 5_134_889]
    p._cpu_generation = 8
    p._record_cpu_result(CpuCoordinatorResult(
        True, "applied", 8, {"attempted": False, "ok": None},
    ), "set_frequency_auto")
    report = p._cpu_gpu_diagnostics()["cpu"]

    snapshot = report["history"][0]["frequency_failure"]
    assert snapshot["requested"] == [419_175, 4_000_000]
    assert snapshot["policies"][0] == {
        "name": "policy0",
        "driver": "amd-pstate-epp",
        "hardware_bounds": [419_175, 5_134_889],
        "target": [419_175, 4_000_000],
        "applied": [419_175, 3_301_000],
        "identity_changed_fields": [],
    }
    assert report["last_failure"]["reason"] == "readback_mismatch"
    assert report["last_failure"]["policies"][0]["target"] == [419_175, 4_000_000]
    assert "frequency_failure" not in report["history"][1]
    assert "private-user" not in str(report)


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


def test_stale_game_frequency_rpc_cannot_retarget_the_active_game(
    tmp_path, monkeypatch
):
    frequency = _FakeFrequency()
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        frequency=frequency,
    )
    p._init()
    p._current_appid = "200"

    asyncio.run(
        p.set_cpu_frequency(
            1_200_000, 2_400_000, scope="game", appid="100"
        )
    )

    assert p._current_appid == "200"
    assert frequency.calls == []
    assert p._cpu_profiles.has_game("100") is False


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


def test_stale_global_frequency_rpc_cannot_apply_after_game_context_changes(
    tmp_path, monkeypatch
):
    frequency = _FakeFrequency()
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        frequency=frequency,
    )
    p._init()
    p._current_appid = "200"

    state = asyncio.run(
        p.set_cpu_frequency(1_200_000, 2_400_000, "global", None, "100")
    )

    assert frequency.calls == []
    assert p._cpu_profiles.effective(None)["frequency"]["manual"] is False
    assert p._current_appid == "200"
    assert state["follows_global"] is True


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


def test_concurrent_cpu_setters_merge_intent_instead_of_dropping_first(
    tmp_path, monkeypatch
):
    smt = _FakeToggle(on=True)
    boost = _FakeToggle(on=True)
    p = _make_plugin(
        tmp_path, monkeypatch, smt=smt, boost=boost, cores=_FakeCores()
    )

    async def yielding_offload(fn):
        await asyncio.sleep(0)
        return fn()

    p._offload_call = yielding_offload

    async def drive():
        await asyncio.gather(
            p.set_smt(False),
            p.set_cpu_boost(False),
        )

    asyncio.run(drive())

    effective = p._cpu_profiles.effective(None)
    assert effective["smt"] is False
    assert effective["boost"] is False
    assert smt.enabled() is False
    assert boost.enabled() is False


def test_transient_cpu_failure_keeps_requested_intent_for_reapply(
    tmp_path, monkeypatch
):
    smt = _FailingToggle(on=True)
    p = _make_plugin(
        tmp_path, monkeypatch, smt=smt,
        boost=_FakeToggle(), cores=_FakeCores(),
    )

    state = asyncio.run(p.set_smt(False))

    assert p._cpu_profiles.effective(None)["smt"] is False
    assert smt.enabled() is True
    assert state["smt"]["enabled"] is True


def test_concurrent_frequency_and_legacy_toggle_keep_both_intents(
    tmp_path, monkeypatch
):
    frequency = _FakeFrequency()
    boost = _FakeToggle(on=True)
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=boost,
        cores=_FakeCores(), frequency=frequency,
    )

    async def yielding_offload(fn):
        await asyncio.sleep(0)
        return fn()

    p._offload_call = yielding_offload

    async def drive():
        await asyncio.gather(
            p.set_cpu_frequency(1_200_000, 2_400_000),
            p.set_cpu_boost(False),
        )

    asyncio.run(drive())

    effective = p._cpu_profiles.effective(None)
    assert effective["frequency"] == {
        "manual": True,
        "min_khz": 1_200_000,
        "max_khz": 2_400_000,
    }
    assert effective["boost"] is False
    assert frequency.requested == (1_200_000, 2_400_000)
    assert boost.enabled() is False


def test_cpu_handoff_retries_transient_release_failure(tmp_path, monkeypatch):
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        cores=_FakeCores(), frequency=_FakeFrequency(),
    )
    outcomes = iter((False, False, True))
    calls = []

    async def release(**kwargs):
        calls.append(kwargs)
        return types.SimpleNamespace(ok=next(outcomes))

    p._apply_cpu_awaited = release

    released = asyncio.run(p._release_cpu_controls("unload"))

    assert released is True
    assert calls == [
        {"enabled": False, "trigger": "unload-1"},
        {"enabled": False, "trigger": "unload-2"},
        {"enabled": False, "trigger": "unload-3"},
    ]


def test_cpu_frequency_reprobes_after_transient_incomplete_startup(
    tmp_path, monkeypatch
):
    import main
    from cpu.frequency import NullCpuFrequency

    recovered = _FakeFrequency()
    p = _make_plugin(
        tmp_path,
        monkeypatch,
        smt=_FakeToggle(),
        boost=_FakeToggle(),
        frequency=NullCpuFrequency("incomplete_policy"),
    )
    p._init()
    p._settings["cpu_frequency_handoff"] = {"version": 1}
    p._cpu_profiles.set_frequency("global", 1_200_000, 2_400_000)
    monkeypatch.setattr(
        main,
        "select_cpu_frequency",
        lambda **_kwargs: recovered,
    )
    p._offload = lambda fn, done=None: (fn(), done() if done else None)

    state = p._cpu_state()

    assert p._cpu_frequency is recovered
    assert recovered.calls == [("manual", 1_200_000, 2_400_000)]
    assert state["frequency"]["manual"] is True


def test_cpu_handoff_is_not_success_while_durable_frequency_needs_reprobe(
    tmp_path, monkeypatch
):
    from cpu.frequency import NullCpuFrequency

    p = _make_plugin(
        tmp_path,
        monkeypatch,
        smt=_FakeToggle(),
        boost=_FakeToggle(),
        frequency=NullCpuFrequency("incomplete_policy"),
    )
    p._init()
    p._settings["cpu_frequency_handoff"] = {"version": 1}

    released = asyncio.run(p._release_cpu_controls("unload"))

    assert released is False


def test_cpu_shutdown_handoff_cannot_be_overwritten_by_late_rpc(
    tmp_path, monkeypatch
):
    smt = _FakeToggle(on=False)
    p = _make_plugin(
        tmp_path, monkeypatch, smt=smt, boost=_FakeToggle(),
        cores=_FakeCores(), frequency=_FakeFrequency(),
    )
    p._init()
    p._cpu_profiles.set_smt("global", False)
    p._cpu_shutdown = True

    async def yielding_offload(fn):
        await asyncio.sleep(0)
        return fn()

    p._offload_call = yielding_offload

    async def drive():
        released, _state = await asyncio.gather(
            p._release_cpu_controls("unload"),
            p.set_smt(False),
        )
        return released

    assert asyncio.run(drive()) is True
    assert smt.enabled() is True


def test_queued_cpu_apply_is_rejected_after_shutdown_generation_advances(
    tmp_path, monkeypatch
):
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        cores=_FakeCores(), frequency=_FakeFrequency(),
    )
    p._init()
    calls = []
    coordinator = types.SimpleNamespace(
        apply=lambda *args, **kwargs: calls.append((args, kwargs))
    )
    p._ensure_cpu_coordinator = lambda: coordinator
    p._cpu_generation = 9

    result = p._run_cpu_apply(p._cpu_intent(), generation=8)

    assert result.ok is False
    assert result.error_code == "stale_generation"
    assert calls == []


def test_manual_cpu_frequency_store_failure_restores_auto_hardware_and_memory(
    tmp_path, monkeypatch
):
    frequency = _FakeFrequency()
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        cores=_FakeCores(), frequency=frequency,
    )
    p._init()

    def fail_save():
        raise OSError("disk full")

    monkeypatch.setattr(p._cpu_profiles, "_save", fail_save)

    state = asyncio.run(p.set_cpu_frequency(1_200_000, 2_400_000))

    assert frequency.requested is None
    assert p._cpu_profiles.effective(None)["frequency"]["manual"] is False
    assert state["frequency"]["status"] == "failed"
    assert state["frequency"]["reason"] == "store_write_failed"


def test_auto_cpu_frequency_store_failure_restores_previous_manual_window(
    tmp_path, monkeypatch
):
    frequency = _FakeFrequency()
    p = _make_plugin(
        tmp_path, monkeypatch, smt=_FakeToggle(), boost=_FakeToggle(),
        cores=_FakeCores(), frequency=frequency,
    )
    asyncio.run(p.set_cpu_frequency(1_200_000, 2_400_000))

    def fail_save():
        raise OSError("disk full")

    monkeypatch.setattr(p._cpu_profiles, "_save", fail_save)

    state = asyncio.run(p.set_cpu_frequency_auto())

    assert frequency.requested == (1_200_000, 2_400_000)
    assert p._cpu_profiles.effective(None)["frequency"] == {
        "manual": True,
        "min_khz": 1_200_000,
        "max_khz": 2_400_000,
    }
    assert state["frequency"]["status"] == "failed"
    assert state["frequency"]["reason"] == "store_write_failed"


def test_cpu_scope_store_failure_restores_previous_game_hardware_and_memory(
    tmp_path, monkeypatch
):
    smt = _FakeToggle(on=True)
    p = _make_plugin(
        tmp_path, monkeypatch, smt=smt, boost=_FakeToggle(),
        cores=_FakeCores(), frequency=_FakeFrequency(),
    )
    p._init()
    p._current_appid = "42"
    asyncio.run(p.set_smt(False, "game", "42"))
    assert smt.enabled() is False
    assert p._cpu_profiles.is_following_global("42") is False

    def fail_save():
        raise OSError("disk full")

    monkeypatch.setattr(p._cpu_profiles, "_save", fail_save)

    state = asyncio.run(p.set_cpu_follow_global(True, "42"))

    assert smt.enabled() is False
    assert p._cpu_profiles.is_following_global("42") is False
    assert state["follows_global"] is False
    assert state["frequency"]["status"] == "failed"
    assert state["frequency"]["reason"] == "store_write_failed"
