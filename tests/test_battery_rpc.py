"""RPC-level tests for battery state + charge limit.

Bootstraps a real Plugin with a fake decky module and a fake TDP backend (so
_init never touches live hardware), then injects a fake charge-limit backend.
"""
import asyncio
import concurrent.futures
import importlib
import sys
import threading
import time
import types

import pytest

from battery.charge_limit import (
    NullChargeLimit,
    SteamDeckChargeLimit,
    SysfsChargeLimit,
)


def _make_plugin(tmp_path, monkeypatch, charge_limit=None):
    fake_decky = types.ModuleType("decky")
    fake_decky.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path)
    fake_decky.DECKY_USER = "deck"
    logs = {"info": [], "warning": [], "error": []}
    fake_decky.logger = types.SimpleNamespace(
        info=lambda *a, **k: logs["info"].append(a),
        warning=lambda *a, **k: logs["warning"].append(a),
        error=lambda *a, **k: logs["error"].append(a),
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

    if charge_limit is not None:
        original_init = main.Plugin._init

        def patched_init(self):
            original_init(self)
            self._charge_limit = charge_limit

        monkeypatch.setattr(main.Plugin, "_init", patched_init)

    plugin = main.Plugin()
    plugin._test_logs = logs
    return plugin


class _FakeChargeLimit:
    adjustable = True
    name = "fake"

    def __init__(self, supported=True):
        self.supported = supported
        self.value = 100

    def get(self):
        return self.value if self.supported else None

    def range(self):
        return (20, 100)

    def set(self, percent):
        if not self.supported:
            return False
        self.value = int(percent)
        return True

    def disable(self):
        if not self.supported:
            return False
        self.value = 100  # ASUS-like: 100 = no cap
        return True


class _FailingChargeLimit(_FakeChargeLimit):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    def set(self, percent):
        self.attempts += 1
        return False


class _FlakyChargeLimit(_FakeChargeLimit):
    def __init__(self):
        super().__init__()
        self.attempts = 0

    def set(self, percent):
        self.attempts += 1
        if self.attempts == 1:
            return False
        return super().set(percent)


class _RecordingChargeLimit(_FakeChargeLimit):
    def __init__(self, supported=True):
        super().__init__(supported=supported)
        self.set_requests = []

    def set(self, percent):
        self.set_requests.append(percent)
        return super().set(percent)


class _ReplaceableChargeLimit(_RecordingChargeLimit):
    def __init__(self, lost=False):
        super().__init__()
        self.lost = lost

    def get(self):
        return None if self.lost else super().get()

    def set(self, percent):
        self.set_requests.append(percent)
        if self.lost:
            return False
        return _FakeChargeLimit.set(self, percent)


class _BlockingChargeLimit(_FakeChargeLimit):
    def __init__(self):
        super().__init__()
        self.release = threading.Event()

    def set(self, percent):
        if not self.release.wait(0.2):
            return False
        return super().set(percent)


class _BlockingFailedWriteChargeLimit(_FakeChargeLimit):
    def __init__(self):
        super().__init__()
        self.write_started = threading.Event()
        self.release_write = threading.Event()
        self.writes = []
        self._first_write = True

    def set(self, percent):
        self.writes.append(int(percent))
        if self._first_write:
            self._first_write = False
            self.write_started.set()
            self.release_write.wait(timeout=1)
            return False
        return super().set(percent)

    def disable(self):
        self.writes.append("off")
        return super().disable()


class _FixedChargeLimit(_RecordingChargeLimit):
    adjustable = False
    name = "lenovo-conservation"

    def __init__(self):
        super().__init__()
        self.conservation_enabled = True
        self.disable_requests = 0

    def get(self):
        return None

    def set(self, percent):
        self.set_requests.append(percent)
        self.conservation_enabled = True
        return True

    def disable(self):
        self.disable_requests += 1
        self.conservation_enabled = False
        return True


class _RecoveringFixedChargeLimit(_FixedChargeLimit):
    def __init__(self, *, set_failures=0, disable_failures=0):
        super().__init__()
        self.set_failures = set_failures
        self.disable_failures = disable_failures

    def set(self, percent):
        self.set_requests.append(percent)
        if self.set_failures > 0:
            self.set_failures -= 1
            return False
        self.conservation_enabled = True
        return True

    def disable(self):
        self.disable_requests += 1
        if self.disable_failures > 0:
            self.disable_failures -= 1
            return False
        self.conservation_enabled = False
        return True


def _late_probe_backend(tmp_path, kind):
    if kind == "sysfs":
        node = tmp_path / "sys/class/power_supply/BAT0/charge_control_end_threshold"
        backend_class = SysfsChargeLimit
    else:
        node = tmp_path / "sys/class/hwmon/hwmon3/max_battery_charge_level"
        backend_class = SteamDeckChargeLimit
        node.parent.mkdir(parents=True, exist_ok=True)
        (node.parent / "name").write_text("steamdeck_hwmon")
    node.parent.mkdir(parents=True, exist_ok=True)
    node.write_text("100")
    return backend_class(root=str(tmp_path))


def test_get_battery_state_shape(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=_FakeChargeLimit())
    state = asyncio.run(p.get_battery_state())
    assert "battery" in state and "charge_limit" in state
    cl = state["charge_limit"]
    assert cl["supported"] is True
    assert cl["enabled"] is False
    assert cl["percent"] == 80
    assert cl["min"] == 20 and cl["max"] == 100


def test_set_charge_limit_enables_and_applies(tmp_path, monkeypatch):
    cl_backend = _FakeChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=cl_backend)
    result = asyncio.run(p.set_charge_limit(True, 70))
    assert result["enabled"] is True
    assert result["percent"] == 70
    assert cl_backend.value == 70  # applied to hardware


def test_set_charge_limit_only_saves_intent_while_module_is_disabled(
    tmp_path, monkeypatch
):
    backend = _RecordingChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["disabled_modules"] = ["chargeLimit"]

    result = asyncio.run(p.set_charge_limit(True, 70))

    assert p._settings["charge_limit_enabled"] is True
    assert p._settings["charge_limit_percent"] == 70
    assert backend.set_requests == []
    assert backend.value == 100
    assert result["managed"] is False


def test_reenabling_charge_limit_reapplies_the_saved_intent(tmp_path, monkeypatch):
    backend = _RecordingChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["disabled_modules"] = ["chargeLimit"]
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 65

    asyncio.run(p.set_ui_module("chargeLimit", False))

    assert "chargeLimit" not in p._settings["disabled_modules"]
    assert backend.set_requests == [65]
    assert backend.value == 65


def test_enabling_charge_limit_while_system_is_off_keeps_handoff_diagnostics(
    tmp_path, monkeypatch
):
    backend = _BlockingFailedWriteChargeLimit()
    candidate = _BlockingFailedWriteChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["disabled_modules"] = ["system", "chargeLimit"]
    p._charge_limit_candidate = candidate

    asyncio.run(p.set_ui_module("chargeLimit", False))

    assert p._settings["disabled_modules"] == ["system"]
    assert backend.writes == []
    assert candidate.writes == []
    assert p._charge_limit_candidate is None
    assert p._charge_limit_reconciliation["status"] == "idle"
    assert p._charge_limit_reconciliation["reason"] == "module_disabled"
    assert p._charge_limit_reconciliation["writes"] == 0


def test_disabling_charge_limit_waits_for_inflight_write_and_prevents_retry(
    tmp_path, monkeypatch
):
    backend = _BlockingFailedWriteChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._reapply_all = lambda on_ac=None: None
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = executor

    async def scenario():
        applying = asyncio.create_task(p.set_charge_limit(True, 80))
        while not backend.write_started.is_set():
            await asyncio.sleep(0)

        disabling = asyncio.create_task(p.set_ui_module("chargeLimit", True))
        await asyncio.sleep(0)
        assert disabling.done() is False

        backend.release_write.set()
        await asyncio.gather(applying, disabling)

    try:
        asyncio.run(scenario())
    finally:
        backend.release_write.set()
        executor.shutdown(wait=True)

    assert backend.writes == [80]
    assert "chargeLimit" in p._settings["disabled_modules"]


def test_disabling_system_waits_for_inflight_charge_write_and_prevents_retry(
    tmp_path, monkeypatch
):
    backend = _BlockingFailedWriteChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._reapply_all = lambda on_ac=None: None
    p._release_gpu_clock = lambda *_: asyncio.sleep(0)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = executor

    async def scenario():
        applying = asyncio.create_task(p.set_charge_limit(True, 80))
        while not backend.write_started.is_set():
            await asyncio.sleep(0)

        disabling = asyncio.create_task(p.set_ui_module("system", True))
        await asyncio.sleep(0)
        assert disabling.done() is False

        backend.release_write.set()
        await asyncio.gather(applying, disabling)

    try:
        asyncio.run(scenario())
    finally:
        backend.release_write.set()
        executor.shutdown(wait=True)

    assert backend.writes == [80]
    assert "system" in p._settings["disabled_modules"]


def test_battery_state_keeps_saved_intent_separate_from_readback(tmp_path, monkeypatch):
    backend = _FakeChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    asyncio.run(p.set_charge_limit(True, 80))
    backend.value = 0

    state = asyncio.run(p.get_battery_state())["charge_limit"]

    assert state["percent"] == 80
    assert state["applied_percent"] == 0
    assert state["backend"] == "fake"


def test_set_charge_limit_clamps_intent_before_persisting(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=_FakeChargeLimit())

    result = asyncio.run(p.set_charge_limit(True, 140))

    assert result["percent"] == 100
    assert p._settings["charge_limit_percent"] == 100


def test_failed_charge_limit_write_keeps_intent_and_reports_readback(tmp_path, monkeypatch):
    backend = _FailingChargeLimit()
    p = _make_plugin(
        tmp_path,
        monkeypatch,
        charge_limit=backend,
    )

    result = asyncio.run(p.set_charge_limit(True, 70))

    assert result["enabled"] is True
    assert backend.attempts == 2
    assert result["percent"] == 70
    assert result["applied_percent"] == 100
    assert result["last_apply"] == {
        "action": "set",
        "requested": 70,
        "ok": False,
        "readback": 100,
        "attempts": 2,
    }
    assert any(
        args[0] == "Charge limit transition %s"
        for args in p._test_logs["warning"]
    )


def test_transient_charge_limit_failure_retries_once(tmp_path, monkeypatch):
    backend = _FlakyChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)

    result = asyncio.run(p.set_charge_limit(True, 70))

    assert backend.attempts == 2
    assert result["percent"] == 70
    assert result["last_apply"] == {
        "action": "set",
        "requested": 70,
        "ok": True,
        "readback": 70,
        "attempts": 2,
    }


def test_disable_writes_no_cap(tmp_path, monkeypatch):
    cl_backend = _FakeChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=cl_backend)
    asyncio.run(p.set_charge_limit(True, 60))
    assert cl_backend.value == 60
    asyncio.run(p.set_charge_limit(False, 60))
    assert cl_backend.value == 100  # disabled -> firmware default


def test_set_charge_limit_persists(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=_FakeChargeLimit())
    asyncio.run(p.set_charge_limit(True, 65))
    # a fresh plugin over the same settings dir reloads the saved values and, at
    # startup, re-applies the persisted limit to hardware (as _reapply_all does).
    cl2 = _FakeChargeLimit()
    p2 = _make_plugin(tmp_path, monkeypatch, charge_limit=cl2)
    p2._init()
    p2._apply_charge_limit()
    assert cl2.value == 65  # persisted limit re-applied to hardware
    cl = asyncio.run(p2.get_battery_state())["charge_limit"]
    assert cl["enabled"] is True and cl["percent"] == 65


def test_full_charge_once_applies_max_without_replacing_saved_limit(
    tmp_path, monkeypatch
):
    backend = _RecordingChargeLimit()
    backend.value = 80
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    monkeypatch.setattr(time, "time", lambda: 1_000.0)

    state = asyncio.run(p.set_charge_limit_full_once(True))

    assert backend.value == 100
    assert p._settings["charge_limit_percent"] == 80
    assert state["full_charge_once"] == {
        "available": True,
        "active": True,
        "status": "active",
        "expires_at": 87_400.0,
    }


def test_full_charge_once_restores_saved_limit_when_battery_is_full(
    tmp_path, monkeypatch
):
    backend = _RecordingChargeLimit()
    backend.value = 80
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._battery = types.SimpleNamespace(
        read=lambda: {"present": True, "percent": 100, "status": "Full"}
    )
    monkeypatch.setattr(time, "time", lambda: 1_000.0)

    async def scenario():
        await p.set_charge_limit_full_once(True)
        await p._check_charge_limit_full_once()
        return p._charge_limit_state()

    state = asyncio.run(scenario())

    assert backend.set_requests == [100, 80]
    assert backend.value == 80
    assert p._settings["charge_limit_full_once_until"] is None
    assert state["full_charge_once"] == {
        "available": True,
        "active": False,
        "status": "inactive",
        "expires_at": None,
    }


def test_full_charge_once_restores_fixed_conservation_mode_after_full_charge(
    tmp_path, monkeypatch
):
    backend = _FixedChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._battery = types.SimpleNamespace(
        read=lambda: {"present": True, "percent": 100, "status": "Full"}
    )
    monkeypatch.setattr(time, "time", lambda: 1_000.0)

    async def scenario():
        started = await p.set_charge_limit_full_once(True)
        assert started["full_charge_once"]["status"] == "active"
        assert backend.conservation_enabled is False
        await p._check_charge_limit_full_once()

    asyncio.run(scenario())

    assert backend.disable_requests == 1
    assert backend.set_requests == [80]
    assert backend.conservation_enabled is True
    assert p._settings["charge_limit_full_once_until"] is None


def test_full_charge_once_keeps_failed_fixed_restoration_visible_until_retry(
    tmp_path, monkeypatch
):
    backend = _RecoveringFixedChargeLimit(set_failures=2)
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._battery = types.SimpleNamespace(
        read=lambda: {"present": True, "percent": 100, "status": "Full"}
    )
    monkeypatch.setattr(time, "time", lambda: 1_000.0)

    async def scenario():
        started = await p.set_charge_limit_full_once(True)
        deadline = started["full_charge_once"]["expires_at"]
        await p._check_charge_limit_full_once()
        failed = p._charge_limit_state()["full_charge_once"]
        await p._check_charge_limit_full_once()
        restored = p._charge_limit_state()["full_charge_once"]
        return deadline, failed, restored

    deadline, failed, restored = asyncio.run(scenario())

    assert backend.conservation_enabled is True
    assert backend.set_requests == [80, 80, 80]
    assert failed == {
        "available": True,
        "active": True,
        "status": "failed",
        "expires_at": deadline,
    }
    assert restored == {
        "available": True,
        "active": False,
        "status": "inactive",
        "expires_at": None,
    }


def test_full_charge_once_retries_failed_fixed_activation_on_monitor_check(
    tmp_path, monkeypatch
):
    backend = _RecoveringFixedChargeLimit(disable_failures=2)
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._battery = types.SimpleNamespace(
        read=lambda: {"present": True, "percent": 60, "status": "Charging"}
    )
    monkeypatch.setattr(time, "time", lambda: 1_000.0)

    async def scenario():
        failed = await p.set_charge_limit_full_once(True)
        await p._check_charge_limit_full_once()
        recovered = p._charge_limit_state()
        return failed, recovered

    failed, recovered = asyncio.run(scenario())

    assert failed["full_charge_once"]["status"] == "failed"
    assert backend.disable_requests == 3
    assert backend.conservation_enabled is False
    assert recovered["full_charge_once"]["status"] == "active"


def test_full_charge_once_restores_limit_when_deadline_expires(
    tmp_path, monkeypatch
):
    backend = _RecordingChargeLimit()
    backend.value = 100
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 75
    p._settings["charge_limit_full_once_until"] = 999.0
    p._charge_limit_full_once_status = "active"
    p._battery = types.SimpleNamespace(
        read=lambda: {"present": True, "percent": 60, "status": "Charging"}
    )
    monkeypatch.setattr(time, "time", lambda: 1_000.0)

    asyncio.run(p._check_charge_limit_full_once())

    assert backend.value == 75
    assert p._settings["charge_limit_full_once_until"] is None


def test_manual_limit_change_cancels_full_charge_once(
    tmp_path, monkeypatch
):
    backend = _RecordingChargeLimit()
    backend.value = 100
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._settings["charge_limit_full_once_until"] = time.time() + 3_600
    p._charge_limit_full_once_status = "active"

    state = asyncio.run(p.set_charge_limit(True, 65))

    assert backend.value == 65
    assert p._settings["charge_limit_full_once_until"] is None
    assert state["full_charge_once"]["active"] is False


@pytest.mark.parametrize("module_id", ["chargeLimit", "system"])
def test_module_handoff_cancels_full_charge_once_without_restoring_limit(
    tmp_path, monkeypatch, module_id
):
    backend = _RecordingChargeLimit()
    backend.value = 100
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._settings["charge_limit_full_once_until"] = time.time() + 3_600
    p._charge_limit_full_once_status = "active"
    p._reapply_all = lambda on_ac=None: None
    p._release_gpu_clock = lambda *_: asyncio.sleep(0)

    asyncio.run(p.set_ui_module(module_id, True))

    assert backend.value == 100
    assert backend.set_requests == []
    assert p._settings["charge_limit_full_once_until"] is None


def test_failed_full_charge_once_write_keeps_retry_intent_visible(
    tmp_path, monkeypatch
):
    backend = _FailingChargeLimit()
    backend.value = 80
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80

    state = asyncio.run(p.set_charge_limit_full_once(True))

    assert backend.attempts == 2
    assert backend.value == 80
    assert state["full_charge_once"]["active"] is True
    assert state["full_charge_once"]["status"] == "failed"


def test_full_charge_once_reconcile_updates_failed_status_after_recovery(
    tmp_path, monkeypatch
):
    backend = _RecordingChargeLimit()
    backend.value = 80
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._settings["charge_limit_full_once_until"] = time.time() + 3_600
    p._charge_limit_full_once_status = "failed"
    p._charge_limit_generation += 1
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))

    asyncio.run(
        p._reconcile_charge_limit(p._charge_limit_generation, "full_once")
    )

    assert backend.value == 100
    assert p._charge_limit_full_once_status == "active"


def test_reconcile_finishes_pending_adjustable_restoration(
    tmp_path, monkeypatch
):
    backend = _RecordingChargeLimit()
    backend.value = 100
    attempts = 0

    def recover_on_reconcile(percent):
        nonlocal attempts
        attempts += 1
        backend.set_requests.append(percent)
        if attempts <= 2:
            return False
        backend.value = percent
        return True

    monkeypatch.setattr(backend, "set", recover_on_reconcile)
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._settings["charge_limit_full_once_until"] = time.time() + 3_600
    p._charge_limit_full_once_status = "active"
    p._battery = types.SimpleNamespace(
        read=lambda: {"present": True, "percent": 100, "status": "Full"}
    )
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    monkeypatch.setattr(p, "_schedule_charge_limit_reconcile", lambda _: None)
    monkeypatch.setattr(p, "_start_charge_limit_full_once_monitor", lambda: None)

    async def scenario():
        await p._check_charge_limit_full_once()
        failed = p._charge_limit_state()["full_charge_once"]
        await p._reconcile_charge_limit(
            p._charge_limit_generation,
            "full_once_restore",
        )
        return failed, p._charge_limit_state()["full_charge_once"]

    failed, restored = asyncio.run(scenario())

    assert failed["status"] == "failed"
    assert restored == {
        "available": True,
        "active": False,
        "status": "inactive",
        "expires_at": None,
    }
    assert backend.set_requests == [80, 80, 80]


def test_persisted_full_charge_once_is_reapplied_after_restart(
    tmp_path, monkeypatch
):
    backend = _RecordingChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._settings["charge_limit_full_once_until"] = time.time() + 3_600
    p._save()

    restarted_backend = _RecordingChargeLimit()
    restarted_backend.value = 80
    restarted = _make_plugin(
        tmp_path, monkeypatch, charge_limit=restarted_backend
    )
    restarted._init()

    restarted._apply_charge_limit()

    assert restarted_backend.value == 100
    assert restarted._settings["charge_limit_percent"] == 80


@pytest.mark.parametrize(
    ("device_key", "kind"),
    [
        ("rog_xbox_ally_x", "sysfs"),
        ("steam_deck_lcd", "deck"),
    ],
)
def test_persisted_full_charge_once_survives_late_backend_probe(
    tmp_path,
    monkeypatch,
    device_key,
    kind,
):
    replacement = _late_probe_backend(tmp_path, kind)
    replacement.set(80)
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._device = types.SimpleNamespace(key=device_key)
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    deadline = time.time() + 3_600
    p._settings["charge_limit_full_once_until"] = deadline
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    monkeypatch.setattr(
        sys.modules["main"],
        "select_charge_limit",
        lambda _: replacement,
    )

    async def scenario():
        p._schedule_charge_limit_reconcile("startup")
        reconcile = p._charge_limit_reconcile_task
        assert reconcile is not None
        p._start_charge_limit_full_once_monitor()
        await reconcile
        state = p._charge_limit_state()["full_charge_once"]
        monitor = p._charge_limit_full_once_task
        p._stop_charge_limit_full_once_monitor()
        if monitor is not None:
            await asyncio.gather(monitor, return_exceptions=True)
        return state

    state = asyncio.run(scenario())

    assert p._charge_limit is replacement
    assert replacement.get() == 100
    assert p._settings["charge_limit_full_once_until"] == deadline
    assert state["active"] is True


def test_corrupt_full_charge_once_deadline_is_removed_at_startup(
    tmp_path, monkeypatch
):
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=_RecordingChargeLimit())
    p._init()
    p._settings["charge_limit_full_once_until"] = "tomorrow"
    p._save()

    restarted = _make_plugin(
        tmp_path,
        monkeypatch,
        charge_limit=_RecordingChargeLimit(),
    )
    restarted._init()
    restarted._start_charge_limit_full_once_monitor()

    assert restarted._settings["charge_limit_full_once_until"] is None


def test_full_charge_once_monitor_recovers_after_a_poll_error(
    tmp_path, monkeypatch
):
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=_RecordingChargeLimit())
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_full_once_until"] = 2_000.0
    monkeypatch.setattr(time, "time", lambda: 1_000.0)
    checks = 0

    async def check():
        nonlocal checks
        checks += 1
        if checks == 1:
            raise OSError("transient read failure")
        p._clear_charge_limit_full_once()

    async def no_wait(_delay):
        return None

    monkeypatch.setattr(p, "_check_charge_limit_full_once", check)
    monkeypatch.setattr(asyncio, "sleep", no_wait)

    asyncio.run(p._charge_limit_full_once_loop(2_000.0))

    assert checks == 2


def test_unsupported_charge_limit_degrades(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=_FakeChargeLimit(supported=False))
    result = asyncio.run(p.set_charge_limit(True, 70))
    assert result["supported"] is False
    assert result["managed"] is False


def test_reconcile_restores_saved_limit_after_external_reset(tmp_path, monkeypatch):
    backend = _FakeChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    backend.set(80)
    backend.value = 100
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,), raising=False)

    p._charge_limit_generation += 1
    asyncio.run(p._reconcile_charge_limit(p._charge_limit_generation, "test"))

    assert backend.value == 80
    assert p._charge_limit_reconciliation == {
        "generation": 1,
        "trigger": "test",
        "status": "recovered",
        "checks": 1,
        "writes": 1,
        "readback": 80,
        "reason": "mismatch_corrected",
        "history": [
            {
                "trigger": "test",
                "check": 1,
                "requested": 80,
                "readback": 100,
                "action": "write",
                "ok": True,
                "backend": "fake",
                "reason": "mismatch_corrected",
            }
        ],
    }


def test_later_match_replaces_failed_reconcile_summary(tmp_path, monkeypatch):
    backend = _FakeChargeLimit()
    reads = iter((100, 100, 80))
    monkeypatch.setattr(backend, "get", lambda: next(reads, 80))
    monkeypatch.setattr(backend, "set", lambda percent: False)
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0, 0.0))

    asyncio.run(
        p._reconcile_charge_limit(p._charge_limit_generation, "test")
    )

    summary = p._charge_limit_reconciliation
    assert summary["status"] == "confirmed"
    assert summary["reason"] == "matched"
    assert summary["readback"] == 80
    assert summary["checks"] == 2
    assert summary["writes"] == 1
    assert summary["history"][-2]["ok"] is False
    assert summary["history"][-1]["ok"] is True


def test_newer_disable_invalidates_reconcile_before_stale_write(tmp_path, monkeypatch):
    backend = _RecordingChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    generation = p._charge_limit_generation
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    read_started = asyncio.Event()
    release_read = asyncio.Event()

    async def paused_offload(operation):
        if operation == backend.get and not read_started.is_set():
            read_started.set()
            await release_read.wait()
        return operation()

    p._offload_call = paused_offload

    async def scenario():
        reconcile = asyncio.create_task(
            p._reconcile_charge_limit(generation, "test")
        )
        await read_started.wait()
        await p.set_charge_limit(False, 80)
        release_read.set()
        await reconcile

    asyncio.run(scenario())

    assert p._charge_limit_generation > generation
    assert backend.set_requests == []
    assert backend.value == 100


def test_shutdown_invalidates_reconcile_before_stale_write(tmp_path, monkeypatch):
    backend = _RecordingChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    generation = p._charge_limit_generation
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))

    p._prepare_shutdown()
    asyncio.run(p._reconcile_charge_limit(generation, "test"))

    assert p._charge_limit_generation > generation
    assert p._charge_limit_reconcile_task is None
    assert backend.set_requests == []


def test_reconcile_replaces_lost_backend_with_same_class(tmp_path, monkeypatch):
    lost = _ReplaceableChargeLimit(lost=True)
    replacement = _ReplaceableChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=lost)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    monkeypatch.setattr(sys.modules["main"], "select_charge_limit", lambda _: replacement)

    asyncio.run(
        p._reconcile_charge_limit(p._charge_limit_generation, "test")
    )

    assert p._charge_limit is replacement
    assert lost.set_requests == []
    assert replacement.set_requests == [80]
    assert replacement.value == 80


def test_reconcile_rejects_different_replacement_class(tmp_path, monkeypatch):
    lost = _ReplaceableChargeLimit(lost=True)
    different = _RecordingChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=lost)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    monkeypatch.setattr(sys.modules["main"], "select_charge_limit", lambda _: different)

    asyncio.run(
        p._reconcile_charge_limit(p._charge_limit_generation, "test")
    )

    assert p._charge_limit is lost
    assert lost.set_requests == []
    assert different.set_requests == []


@pytest.mark.parametrize(
    ("device_key", "kind", "backend_class"),
    [
        ("rog_xbox_ally_x", "sysfs", SysfsChargeLimit),
        ("steam_deck_oled", "deck", SteamDeckChargeLimit),
    ],
)
def test_exact_profile_can_gain_supported_backend_late(
    tmp_path, monkeypatch, device_key, kind, backend_class
):
    replacement = _late_probe_backend(tmp_path, kind)
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._device = types.SimpleNamespace(key=device_key)
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    monkeypatch.setattr(sys.modules["main"], "select_charge_limit", lambda _: replacement)

    asyncio.run(
        p._reconcile_charge_limit(p._charge_limit_generation, "test")
    )

    assert isinstance(p._charge_limit, backend_class)
    assert p._charge_limit.get() == 80
    assert p._charge_limit_reconciliation["status"] == "recovered"
    assert p._charge_limit_reconciliation["history"][-1]["action"] == "write"


def test_exact_profile_rejects_unreadable_late_probe_candidate(
    tmp_path, monkeypatch
):
    candidate = _late_probe_backend(tmp_path, "sysfs")
    set_requests = []
    monkeypatch.setattr(candidate, "get", lambda: None)
    monkeypatch.setattr(
        candidate,
        "set",
        lambda percent: (set_requests.append(percent), False)[1],
    )
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._device = types.SimpleNamespace(key="rog_xbox_ally_x")
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    monkeypatch.setattr(sys.modules["main"], "select_charge_limit", lambda _: candidate)

    asyncio.run(
        p._reconcile_charge_limit(p._charge_limit_generation, "test")
    )

    state = p._charge_limit_state()
    assert isinstance(p._charge_limit, NullChargeLimit)
    assert state["supported"] is False
    assert state["backend"] == "unsupported"
    assert set_requests == []
    assert p._charge_limit_reconciliation["status"] == "failed"
    assert p._charge_limit_reconciliation["checks"] == 1
    assert p._charge_limit_reconciliation["history"][-1]["action"] == "unavailable"


def test_exact_profile_rejects_unwritable_late_probe_candidate(
    tmp_path, monkeypatch
):
    candidate = _late_probe_backend(tmp_path, "sysfs")
    set_requests = []
    monkeypatch.setattr(
        candidate,
        "set",
        lambda percent: (set_requests.append(percent), False)[1],
    )
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._device = types.SimpleNamespace(key="rog_xbox_ally_x")
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    monkeypatch.setattr(sys.modules["main"], "select_charge_limit", lambda _: candidate)

    asyncio.run(
        p._reconcile_charge_limit(p._charge_limit_generation, "test")
    )

    state = p._charge_limit_state()
    assert isinstance(p._charge_limit, NullChargeLimit)
    assert state["supported"] is False
    assert state["backend"] == "unsupported"
    assert set_requests == [80]


@pytest.mark.parametrize(
    (
        "case",
        "expected_reason",
        "expected_backend",
        "expected_readback",
        "expected_action",
        "expected_writes",
    ),
    [
        ("no_candidate", "no_candidate", "unsupported", None, "unavailable", 0),
        ("wrong_class", "wrong_class", "fake", None, "unavailable", 0),
        ("unreadable", "unreadable", "sysfs-threshold", None, "unavailable", 0),
        ("write_rejected", "write_rejected", "sysfs-threshold", 100, "write", 1),
        (
            "confirmation_failed",
            "confirmation_failed",
            "sysfs-threshold",
            100,
            "write",
            1,
        ),
    ],
)
def test_late_probe_reports_allowlisted_failure_reason(
    tmp_path,
    monkeypatch,
    case,
    expected_reason,
    expected_backend,
    expected_readback,
    expected_action,
    expected_writes,
):
    if case == "no_candidate":
        candidate = NullChargeLimit()
    elif case == "wrong_class":
        candidate = _RecordingChargeLimit()
    else:
        candidate = _late_probe_backend(tmp_path, "sysfs")
        if case == "unreadable":
            monkeypatch.setattr(candidate, "get", lambda: None)
        elif case == "write_rejected":
            monkeypatch.setattr(candidate, "set", lambda percent: False)
        else:
            monkeypatch.setattr(candidate, "set", lambda percent: True)

    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._device = types.SimpleNamespace(key="rog_xbox_ally_x")
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    monkeypatch.setattr(sys.modules["main"], "select_charge_limit", lambda _: candidate)

    asyncio.run(
        p._reconcile_charge_limit(p._charge_limit_generation, "test")
    )

    summary = p._charge_limit_reconciliation
    assert summary["status"] == "failed"
    assert summary["reason"] == expected_reason
    assert summary["readback"] == expected_readback
    assert summary["writes"] == expected_writes
    assert summary["history"][-1] == {
        "trigger": "test",
        "check": 1,
        "requested": 80,
        "readback": expected_readback,
        "action": expected_action,
        "ok": False,
        "backend": expected_backend,
        "reason": expected_reason,
    }
    assert isinstance(p._charge_limit, NullChargeLimit)


def test_failed_private_candidate_is_consumed_once(tmp_path, monkeypatch):
    candidate = _FailingChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_candidate = candidate

    p._apply_charge_limit()
    p._apply_charge_limit()

    assert candidate.attempts == 2
    assert p._charge_limit_candidate is None


@pytest.mark.parametrize("action", ["cancel", "reschedule", "shutdown"])
def test_private_candidate_is_cleared_at_lifecycle_boundary(
    tmp_path, monkeypatch, action
):
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._charge_limit_candidate = _FakeChargeLimit()

    if action == "cancel":
        p._cancel_charge_limit_reconcile("test")
    elif action == "reschedule":
        p._schedule_charge_limit_reconcile("test")
    else:
        p._prepare_shutdown()

    assert p._charge_limit_candidate is None


def test_cancelled_probe_task_clears_private_candidate(tmp_path, monkeypatch):
    candidate = _late_probe_backend(tmp_path, "sysfs")
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._device = types.SimpleNamespace(key="rog_xbox_ally_x")
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    generation = p._charge_limit_generation
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    monkeypatch.setattr(sys.modules["main"], "select_charge_limit", lambda _: candidate)
    confirmation_started = asyncio.Event()
    candidate_reads = 0

    async def controlled_offload(operation):
        nonlocal candidate_reads
        if (
            getattr(operation, "__self__", None) is candidate
            and getattr(operation, "__name__", "") == "get"
        ):
            candidate_reads += 1
            if candidate_reads == 2:
                confirmation_started.set()
                await asyncio.Event().wait()
        return operation()

    p._offload_call = controlled_offload

    async def scenario():
        reconcile = asyncio.create_task(
            p._reconcile_charge_limit(generation, "test")
        )
        await confirmation_started.wait()
        reconcile.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reconcile

    asyncio.run(scenario())

    assert p._charge_limit_candidate is None


def test_reapply_transfers_private_candidate_once_for_null_backend(
    tmp_path, monkeypatch
):
    candidate = _FailingChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._device = types.SimpleNamespace(key="rog_xbox_ally_x")
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_candidate = candidate

    for name in (
        "_cancel_color_revert",
        "_apply_cpu",
        "_apply_gpu_clock",
        "_schedule_tdp_apply",
        "_reapply_fans",
        "_reapply_hdr",
        "_reapply_color",
        "_reapply_audio",
        "_reapply_controller",
        "_schedule_hud_apply",
    ):
        monkeypatch.setattr(p, name, lambda *args: None)
    monkeypatch.setattr(p, "_tdp_control_on", lambda: True)

    def immediate_offload(operation, done=None):
        operation()
        if done is not None:
            done()

    monkeypatch.setattr(p, "_offload", immediate_offload)
    monkeypatch.setattr(
        p, "_schedule_charge_limit_reconcile", lambda trigger: None
    )

    p._reapply_all()
    p._reapply_all()

    assert candidate.attempts == 2
    assert p._charge_limit_candidate is None


def test_latest_of_two_queued_intents_applies_private_candidate(
    tmp_path, monkeypatch
):
    candidate = _late_probe_backend(tmp_path, "sysfs")
    candidate.set(80)
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_candidate = candidate
    first_offload_started = asyncio.Event()
    release_first_offload = asyncio.Event()
    serial_lock = asyncio.Lock()
    offload_calls = 0

    async def controlled_offload(operation):
        nonlocal offload_calls
        async with serial_lock:
            offload_calls += 1
            if offload_calls == 1:
                first_offload_started.set()
                await release_first_offload.wait()
            return operation()

    p._offload_call = controlled_offload
    monkeypatch.setattr(
        p, "_schedule_charge_limit_reconcile", lambda trigger: None
    )

    async def scenario():
        first = asyncio.create_task(p.set_charge_limit(False, 80))
        await first_offload_started.wait()
        second = asyncio.create_task(p.set_charge_limit(True, 60))
        while p._settings["charge_limit_percent"] != 60:
            await asyncio.sleep(0)
        release_first_offload.set()
        await asyncio.gather(first, second)

    asyncio.run(scenario())

    assert candidate.get() == 60
    assert p._charge_limit_candidate is None
    assert isinstance(p._charge_limit, NullChargeLimit)


def test_selected_backend_skips_retry_after_newer_intent(
    tmp_path, monkeypatch
):
    backend = _BlockingFailedWriteChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = executor

    async def scenario():
        old = asyncio.create_task(p.set_charge_limit(True, 80))
        while not backend.write_started.is_set():
            await asyncio.sleep(0)
        latest = asyncio.create_task(p.set_charge_limit(False, 80))
        while p._settings["charge_limit_enabled"]:
            await asyncio.sleep(0)
        backend.release_write.set()
        await asyncio.gather(old, latest)

    try:
        asyncio.run(scenario())
    finally:
        backend.release_write.set()
        executor.shutdown(wait=True)

    assert backend.writes == [80, "off"]
    assert backend.value == 100


def test_private_candidate_skips_retry_after_newer_intent(
    tmp_path, monkeypatch
):
    candidate = _BlockingFailedWriteChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._charge_limit_candidate = candidate
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = executor

    async def scenario():
        old = asyncio.create_task(p.set_charge_limit(True, 80))
        while not candidate.write_started.is_set():
            await asyncio.sleep(0)
        latest = asyncio.create_task(p.set_charge_limit(False, 80))
        while p._settings["charge_limit_enabled"]:
            await asyncio.sleep(0)
        candidate.release_write.set()
        await asyncio.gather(old, latest)

    try:
        asyncio.run(scenario())
    finally:
        candidate.release_write.set()
        executor.shutdown(wait=True)

    assert candidate.writes == [80, "off"]
    assert candidate.value == 100
    assert p._charge_limit_candidate is None


def test_cancelled_queued_intent_still_applies_private_candidate(
    tmp_path, monkeypatch
):
    candidate = _late_probe_backend(tmp_path, "sysfs")
    candidate.set(80)
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._device = types.SimpleNamespace(key="rog_xbox_ally_x")
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_candidate = candidate
    worker_started = threading.Event()
    release_worker = threading.Event()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    p._apply_executor = executor

    def block_worker():
        worker_started.set()
        release_worker.wait(timeout=1)

    executor.submit(block_worker)

    async def scenario():
        while not worker_started.is_set():
            await asyncio.sleep(0)
        rpc = asyncio.create_task(p.set_charge_limit(False, 80))
        while not p._offload_futures:
            await asyncio.sleep(0)
        rpc.cancel()
        with pytest.raises(asyncio.CancelledError):
            await rpc
        release_worker.set()
        await p._drain_offloaded()
        for _ in range(20):
            if (
                p._charge_limit_reconciliation["trigger"]
                == "set_charge_limit"
            ):
                break
            await asyncio.sleep(0)
        reconcile = p._charge_limit_reconcile_task
        if reconcile is not None:
            reconcile.cancel()

    try:
        asyncio.run(scenario())
    finally:
        release_worker.set()
        executor.shutdown(wait=True)

    assert candidate.get() == 100
    assert p._charge_limit_candidate is None
    assert p._charge_limit_reconciliation["trigger"] == "set_charge_limit"


def test_latest_of_two_queued_reapplies_applies_private_candidate(
    tmp_path, monkeypatch
):
    candidate = _late_probe_backend(tmp_path, "sysfs")
    candidate.set(80)
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._device = types.SimpleNamespace(key="rog_xbox_ally_x")
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 70
    p._charge_limit_candidate = candidate

    for name in (
        "_cancel_color_revert",
        "_apply_cpu",
        "_apply_gpu_clock",
        "_schedule_tdp_apply",
        "_reapply_fans",
        "_reapply_hdr",
        "_reapply_color",
        "_reapply_audio",
        "_reapply_controller",
        "_schedule_hud_apply",
    ):
        monkeypatch.setattr(p, name, lambda *args: None)
    monkeypatch.setattr(p, "_tdp_control_on", lambda: True)
    queued = []
    monkeypatch.setattr(
        p,
        "_offload",
        lambda operation, done=None: queued.append((operation, done)),
    )
    monkeypatch.setattr(
        p, "_schedule_charge_limit_reconcile", lambda trigger: None
    )

    p._reapply_all()
    p._settings["charge_limit_percent"] = 60
    p._reapply_all()
    for operation, done in queued:
        operation()
        if done is not None:
            done()

    assert candidate.get() == 60
    assert p._charge_limit_candidate is None
    assert isinstance(p._charge_limit, NullChargeLimit)


def test_newer_disable_reaches_private_candidate_without_stale_promotion(
    tmp_path, monkeypatch
):
    candidate = _late_probe_backend(tmp_path, "sysfs")
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._device = types.SimpleNamespace(key="rog_xbox_ally_x")
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    generation = p._charge_limit_generation
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    monkeypatch.setattr(sys.modules["main"], "select_charge_limit", lambda _: candidate)
    confirmation_started = asyncio.Event()
    release_confirmation = asyncio.Event()
    candidate_reads = 0

    async def controlled_offload(operation):
        nonlocal candidate_reads
        if (
            getattr(operation, "__self__", None) is candidate
            and getattr(operation, "__name__", "") == "get"
        ):
            candidate_reads += 1
            if candidate_reads == 2:
                confirmation_started.set()
                await release_confirmation.wait()
        return operation()

    p._offload_call = controlled_offload

    async def scenario():
        old_reconcile = asyncio.create_task(
            p._reconcile_charge_limit(generation, "old")
        )
        await confirmation_started.wait()
        disabled = await p.set_charge_limit(False, 80)
        diagnostics = p._charge_limit_reconciliation
        disabled_value = candidate.get()
        release_confirmation.set()
        await old_reconcile
        return disabled, disabled_value, diagnostics

    disabled, disabled_value, diagnostics = asyncio.run(scenario())

    assert disabled["supported"] is False
    assert disabled_value == 100
    assert isinstance(p._charge_limit, NullChargeLimit)
    assert p._charge_limit_reconciliation == diagnostics
    assert p._charge_limit_reconciliation["generation"] > generation


def test_newer_disable_prevents_stale_post_write_diagnostics(
    tmp_path, monkeypatch
):
    backend = _RecordingChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    generation = p._charge_limit_generation
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    confirmation_started = asyncio.Event()
    release_confirmation = asyncio.Event()
    backend_reads = 0

    async def controlled_offload(operation):
        nonlocal backend_reads
        if operation == backend.get:
            backend_reads += 1
            if backend_reads == 2:
                confirmation_started.set()
                await release_confirmation.wait()
        return operation()

    p._offload_call = controlled_offload

    async def scenario():
        old_reconcile = asyncio.create_task(
            p._reconcile_charge_limit(generation, "old")
        )
        await confirmation_started.wait()
        await p.set_charge_limit(False, 80)
        diagnostics = p._charge_limit_reconciliation
        release_confirmation.set()
        await old_reconcile
        return diagnostics

    diagnostics = asyncio.run(scenario())

    assert backend.value == 100
    assert p._charge_limit_reconciliation == diagnostics
    assert p._charge_limit_reconciliation["generation"] > generation


@pytest.mark.parametrize(
    "device_key",
    ["msi_claw_8_ai_plus", "generic", "rog_future"],
)
def test_late_probe_does_not_expand_null_backend_support(
    tmp_path, monkeypatch, device_key
):
    replacement = _late_probe_backend(tmp_path, "sysfs")
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=NullChargeLimit())
    p._init()
    p._device = types.SimpleNamespace(key=device_key)
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    p._charge_limit_generation += 1
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))
    monkeypatch.setattr(sys.modules["main"], "select_charge_limit", lambda _: replacement)

    asyncio.run(
        p._reconcile_charge_limit(p._charge_limit_generation, "test")
    )

    assert isinstance(p._charge_limit, NullChargeLimit)
    assert replacement.get() == 100


def test_set_charge_limit_offloads_apply_and_schedules_reconcile(
    tmp_path, monkeypatch
):
    backend = _BlockingChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)

    async def scenario():
        asyncio.get_running_loop().call_later(0.01, backend.release.set)
        result = await p.set_charge_limit(True, 80)
        task = p._charge_limit_reconcile_task
        assert task is not None
        assert not task.done()
        task.cancel()
        return result

    result = asyncio.run(scenario())

    assert result["applied_percent"] == 80
    assert result["reconciliation"]["trigger"] == "set_charge_limit"


def test_reapply_offloads_charge_limit_before_scheduling_reconcile(
    tmp_path, monkeypatch
):
    backend = _RecordingChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    events = []

    for name in (
        "_cancel_color_revert",
        "_apply_cpu",
        "_apply_gpu_clock",
        "_schedule_tdp_apply",
        "_reapply_fans",
        "_reapply_hdr",
        "_reapply_color",
        "_reapply_audio",
        "_reapply_controller",
        "_schedule_hud_apply",
    ):
        monkeypatch.setattr(p, name, lambda *args: None)
    monkeypatch.setattr(p, "_tdp_control_on", lambda: True)

    def immediate_offload(operation, done=None):
        events.append("offload")
        operation()
        events.append("apply")
        if done is not None:
            done()

    monkeypatch.setattr(p, "_offload", immediate_offload)
    original_schedule = p._schedule_charge_limit_reconcile

    def record_schedule(trigger):
        events.append("schedule")
        original_schedule(trigger)

    monkeypatch.setattr(p, "_schedule_charge_limit_reconcile", record_schedule)

    async def scenario():
        p._reapply_all()
        assert p._charge_limit_reconcile_task is not None
        p._charge_limit_reconcile_task.cancel()

    asyncio.run(scenario())

    assert events[:3] == ["offload", "apply", "schedule"]
    assert backend.set_requests == [80]


def test_scheduler_reports_fixed_backend_as_unverifiable(tmp_path, monkeypatch):
    backend = _FixedChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80

    p._schedule_charge_limit_reconcile("test")

    assert backend.set_requests == []
    assert p._charge_limit_reconcile_task is None
    assert p._charge_limit_reconciliation["status"] == "unverifiable"
    assert p._charge_limit_reconciliation["reason"] == "fixed_threshold"
    assert p._charge_limit_reconciliation["readback"] is None
    assert p._charge_limit_reconciliation["writes"] == 0


def test_reconcile_history_keeps_only_eight_allowlisted_events(
    tmp_path, monkeypatch
):
    backend = _FakeChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0,))

    async def scenario():
        for index in range(10):
            p._charge_limit_generation += 1
            await p._reconcile_charge_limit(
                p._charge_limit_generation, f"test-{index}"
            )

    asyncio.run(scenario())

    history = p._charge_limit_reconciliation["history"]
    assert len(history) == 8
    assert history[0]["trigger"] == "test-2"
    assert set(history[-1]) == {
        "trigger",
        "check",
        "requested",
        "readback",
        "action",
        "ok",
        "backend",
        "reason",
    }


def test_reconcile_publishes_each_check_before_next_delay(tmp_path, monkeypatch):
    backend = _FakeChargeLimit()
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=backend)
    p._init()
    p._settings["charge_limit_enabled"] = True
    p._settings["charge_limit_percent"] = 80
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (0.0, 3600.0))

    async def scenario():
        p._schedule_charge_limit_reconcile("test")

        async def first_check_finished():
            while not p._charge_limit_history:
                await asyncio.sleep(0.001)

        await asyncio.wait_for(first_check_finished(), timeout=1.0)
        snapshot = dict(p._charge_limit_reconciliation)
        p._charge_limit_reconcile_task.cancel()
        return snapshot

    snapshot = asyncio.run(scenario())

    assert snapshot["status"] == "recovered"
    assert snapshot["checks"] == 1
    assert snapshot["writes"] == 1
    assert snapshot["readback"] == 80
    assert len(snapshot["history"]) == 1


def test_new_schedule_cancels_previous_reconcile_task(tmp_path, monkeypatch):
    p = _make_plugin(tmp_path, monkeypatch, charge_limit=_FakeChargeLimit())
    p._init()
    p._settings["charge_limit_enabled"] = True
    monkeypatch.setattr(p, "_charge_limit_verify_delays", (3600.0,))

    async def scenario():
        p._schedule_charge_limit_reconcile("first")
        first = p._charge_limit_reconcile_task
        p._schedule_charge_limit_reconcile("second")
        second = p._charge_limit_reconcile_task
        await asyncio.sleep(0)
        assert first.cancelled()
        assert second is not first
        assert not second.done()
        second.cancel()

    asyncio.run(scenario())
