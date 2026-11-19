from pathlib import Path

import pytest

from cpu.controls import CoreControl
from cpu.gpd_win5 import GpdWin5Cores, select_core_control


DMI = ("GPD", "G1618-05")
# Masks and hotplug error from the G1618-05 report with a 16-core profile.
MASKS = ("0-31", "0-7,16-23", "0-7,16-24", "0-7,9,16-26")
PROFILE = {"cores": 16, "smt": True, "frequency": {"manual": False}}


def cpus(spec):
    result = set()
    for part in spec.split(","):
        start, _, end = part.partition("-")
        result.update(range(int(start), int(end or start) + 1))
    return result


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(value))


def tree(root, dmi=DMI):
    for name, val in zip(("sys_vendor", "product_name"), dmi):
        put(root / "sys/class/dmi/id" / name, val)
    base = root / "sys/devices/system/cpu"
    put(base / "present", MASKS[0])
    put(base / "smt/control", "on")
    for cpu in range(32):
        put(base / f"cpu{cpu}/topology/core_id", cpu % 16)
    mask(base, MASKS[0])
    return base


def mask(base, spec):
    present = cpus(spec)
    for cpu in range(1, 32):
        put(base / f"cpu{cpu}/online", int(cpu in present))
    put(base / "online", spec)


@pytest.mark.parametrize("dmi", [("Valve", "Jupiter"), ("LENOVO", "83E1"),
                                 ("GPD", "G1618-04"), ("Other", DMI[1])])
def test_selection_preserves_other_devices(tmp_path, dmi):
    tree(tmp_path, dmi)
    assert type(select_core_control(tmp_path)) is CoreControl


def test_reported_parking_is_preserved_on_probe_reapply_and_release(tmp_path, monkeypatch):
    base = tree(tmp_path)
    cores = select_core_control(tmp_path)
    assert isinstance(cores, GpdWin5Cores)
    writes = []
    monkeypatch.setattr("cpu.gpd_win5.write_str", lambda path, val: writes.append((path, val)))
    for spec in MASKS[1:]:
        mask(base, spec)
        cores = select_core_control(tmp_path)
        with cores.transaction():
            assert cores.apply_profile(PROFILE, None, []) is None
            assert cores.release()
        assert cores.max_cores == 16
        assert cores.active() == len({i % 16 for i in cpus(spec)})
    assert not writes


def coordinator(cores):
    from cpu.gpd_win5 import GpdWin5Coordinator
    return GpdWin5Coordinator(cores, None, None, None)


def test_manual_failure_with_online_sibling_rolls_back_only_this_request(tmp_path, monkeypatch):
    base = tree(tmp_path)
    cores = select_core_control(tmp_path)
    mask(base, MASKS[-1])  # CPU24 is online while CPU8 fails to come back.
    # One external CPU can come back before the first rejected CPU.
    put(base / "cpu7/online", 0)
    calls = []

    def write(path, value):
        path = Path(path)
        calls.append((path.parent.name, value))
        if path.parent.name == "cpu8":
            return False
        path.write_text(str(value))
        return True

    monkeypatch.setattr("cpu.gpd_win5.write_str", write)
    controller = coordinator(cores)
    manual = {**PROFILE, "_manual_topology": "cores"}
    failed = controller.apply(manual, 1)
    assert failed.error_code == "cores_write_failed" and failed.rollback["ok"]
    assert calls == [("cpu7", 1), ("cpu8", 1), ("cpu7", 0)]
    assert (base / "cpu24/online").read_text() == "1"
    calls.clear()
    assert controller.apply(PROFILE, 2).status == "clamped"
    assert controller.apply(PROFILE, 3, enabled=False).ok
    assert calls == []


def test_reload_and_sleep_release_only_owned_threads(tmp_path):
    base = tree(tmp_path)
    cores = select_core_control(tmp_path)
    mask(base, MASKS[1])
    assert coordinator(cores).apply({**PROFILE, "cores": 6}, 1).ok
    assert cores.active() == 6
    for i in (6, 7, 22, 23):
        assert (base / f"cpu{i}/online").read_text() == "0"
        (base / f"cpu{i}/topology/core_id").unlink()
    # The same-boot map and ownership survive a Decky reload.
    reloaded = select_core_control(tmp_path)
    assert reloaded.max_cores == 16
    from cpu.gpd_sleep import restore
    assert restore(tmp_path)
    assert {i for i in range(32) if reloaded._online(i)} == cpus(MASKS[1])


def test_incomplete_first_probe_recovers_passively(tmp_path):
    base = tree(tmp_path)
    mask(base, MASKS[1])
    (base / "cpu8/topology/core_id").unlink()
    cores = select_core_control(tmp_path)
    assert cores.max_cores is None
    assert coordinator(cores).apply({**PROFILE, "_manual_topology": "cores"}, 1).error_code == "topology_unavailable"
    assert (base / "cpu8/online").read_text() == "0"
    put(base / "cpu8/topology/core_id", 8)
    coordinator(cores).apply(PROFILE, 2)
    assert cores.max_cores == 16


def test_owned_failure_is_not_retried_by_automatic_or_sleep_paths(tmp_path, monkeypatch):
    tree(tmp_path)
    cores = select_core_control(tmp_path)
    ctrl = coordinator(cores)
    assert ctrl.apply({**PROFILE, "cores": 8}, 1).ok
    calls = []

    def fail(path, value):
        name = Path(path).parent.name
        calls.append((name, value))
        if name == "cpu8":
            return False
        Path(path).write_text(str(value))
        return True

    monkeypatch.setattr("cpu.gpd_win5.write_str", fail)
    assert not ctrl.apply(PROFILE, 2).ok
    previous = list(calls)
    assert previous == [("cpu8", 1)]
    assert not ctrl.apply(PROFILE, 3, enabled=False).ok
    assert calls.count(("cpu8", 1)) == 1
    assert calls[-1] == ("cpu31", 1)
    assert all(cores._online(i) == 1 for i in range(32) if i != 8)
    with cores.transaction():
        assert not cores.release()
    assert not ctrl.apply({**PROFILE, "_manual_topology": "cores"}, 4).ok
    assert calls.count(("cpu8", 1)) == 2


def test_generation_change_rolls_back_verified_writes(tmp_path, monkeypatch):
    tree(tmp_path)
    cores = select_core_control(tmp_path)
    calls = []
    def write(path, value):
        calls.append(value)
        Path(path).write_text(str(value))
        return True

    monkeypatch.setattr("cpu.gpd_win5.write_str", write)
    result = coordinator(cores).apply({**PROFILE, "cores": 7}, 1, is_current=lambda: not calls)
    assert result.error_code == "stale_generation" and result.rollback["ok"]
    assert calls == [0, 0, 1, 1]
    assert all(cores._online(i) == 1 for i in range(32))


def test_smt_switch_preserves_foreign_parking_on_sleep_and_handoff(tmp_path, monkeypatch):
    base = tree(tmp_path)
    cores = select_core_control(tmp_path)
    ctrl = coordinator(cores)
    calls = []

    def kernel_write(path, value):
        path = Path(path)
        calls.append((path.name, value))
        path.write_text(str(value))
        if path == base / "smt/control":
            for i in range(16, 32):
                put(base / f"cpu{i}/online", int(value == "on"))
        return True

    monkeypatch.setattr("cpu.gpd_win5.write_str", kernel_write)
    mask(base, MASKS[1])
    assert not ctrl.apply({**PROFILE, "smt": False, "_manual_topology": "smt"}, 1).ok
    assert calls == []
    mask(base, MASKS[0])
    assert ctrl.apply({**PROFILE, "smt": False, "_manual_topology": "smt"}, 2).ok
    assert calls == [("control", "off")]
    put(base / "cpu8/online", 0)
    reloaded = select_core_control(tmp_path)
    with reloaded.transaction():
        assert not reloaded.release()
    assert calls == [("control", "off")]
    put(base / "cpu8/online", 1)
    with reloaded.transaction():
        assert reloaded.release()
    assert calls == [("control", "off"), ("control", "on")]


def test_manual_failure_does_not_save_or_replay_profile(tmp_path, monkeypatch):
    import asyncio
    import importlib
    from cpu.sleep_guard import SleepCoreGuard
    from test_cpu_rpc import _make_plugin

    plugin = _make_plugin(tmp_path, monkeypatch)
    main = importlib.import_module("main")
    base = tree(tmp_path)
    cores = select_core_control(tmp_path)
    monkeypatch.setattr(main, "select_core_control", lambda: cores)
    monkeypatch.setattr(main, "SleepCoreGuard", lambda **kw: SleepCoreGuard(tmp_path, lambda *_: True, loaded_command=lambda: "gpd_sleep.py", **kw))
    plugin._init()
    mask(base, MASKS[-1])
    previous = plugin._cpu_profiles.effective(None)
    attempts = []
    def reject(path, value):
        attempts.append((Path(path).parent.name, value))
        return False

    monkeypatch.setattr("cpu.gpd_win5.write_str", reject)
    asyncio.run(plugin.set_active_cores(15))
    assert plugin._cpu_last_result.error_code == "cores_write_failed"
    assert attempts == [("cpu8", 1)]
    assert plugin._cpu_profiles.effective(None) == previous
    assert "gpd_sleep.py" in Path(plugin._sleep_core_guard._unit).read_text()


def test_save_failure_reverts_manually_awakened_external_cpu(tmp_path):
    base = tree(tmp_path)
    cores = select_core_control(tmp_path)
    mask(base, MASKS[2])
    original = [cores._online(i) for i in range(32)]

    def fail_save():
        raise OSError("read-only filesystem")

    intent = {**PROFILE, "_manual_topology": "cores", "_persist_topology": fail_save}
    result = coordinator(cores).apply(intent, 1)
    assert result.error_code == "store_write_failed" and result.rollback["ok"]
    assert [cores._online(i) for i in range(32)] == original
    with cores.transaction():
        assert cores.release()
    assert [cores._online(i) for i in range(32)] == original


def test_partial_smt_disable_reverts_confirmed_sibling_only(tmp_path, monkeypatch):
    base = tree(tmp_path)
    cores = select_core_control(tmp_path)
    calls = []

    def partial(path, value):
        path = Path(path)
        calls.append((path.name, str(value)))
        if path.name == "control":
            put(base / "cpu16/online", 0)
            # Independent parking during the global SMT syscall.
            put(base / "cpu8/online", 0)
            return False
        path.write_text(str(value))
        return True

    monkeypatch.setattr("cpu.gpd_win5.write_str", partial)
    result = coordinator(cores).apply({**PROFILE, "smt": False, "_manual_topology": "smt"}, 1)
    assert result.error_code == "smt_write_failed" and result.rollback["ok"]
    assert calls == [("control", "off"), ("online", "1")]
    assert cores._online(16) == 1 and cores._online(8) == 0


def test_write_receipt_failure_rolls_back_before_unlocking(tmp_path, monkeypatch):
    tree(tmp_path)
    cores = select_core_control(tmp_path)
    save = cores._save
    def fail_once():
        if cores.state.get("owned") and not cores.state.get("pending"):
            monkeypatch.setattr(cores, "_save", save)
            raise OSError("receipt unavailable")
        save()

    monkeypatch.setattr(cores, "_save", fail_once)
    result = coordinator(cores).apply({**PROFILE, "cores": 8}, 1)
    assert result.error_code == "topology_state_unavailable" and result.rollback["ok"]
    assert cores.active() == 16
    with cores.transaction():
        assert not cores.state.get("owned")


def test_legacy_guard_is_replaced_and_reload_failure_is_retried(tmp_path):
    from cpu.sleep_guard import SleepCoreGuard

    previous = SleepCoreGuard(tmp_path, lambda *_: True)
    assert previous.ensure()
    loaded = {"command": "/bin/sh old", "enabled": True}
    replies = iter([False, True])
    def systemctl(*args):
        if args[0] == "disable":
            assert args[1:] == ("--runtime", "--now", "panel-de-control-sleep-cores.service")
            loaded.update(command="", enabled=False)
            return True
        if next(replies):
            loaded.update(command="/usr/bin/python3 .../gpd_sleep.py", enabled=True)
            return True
        return False

    scoped = SleepCoreGuard(tmp_path, systemctl, gpd_win5=True, loaded_command=lambda: loaded["command"])
    assert not scoped.ensure() and not scoped.ready
    assert not loaded["enabled"]
    assert "gpd_sleep.py" in Path(scoped._unit).read_text()
    assert not previous.installed
    assert scoped.ensure() and scoped.ready and loaded["enabled"]


def test_partial_maps_accumulate_without_waking_parked_cpus(tmp_path):
    base = tree(tmp_path)
    mask(base, MASKS[1])
    (base / "cpu8/topology/core_id").unlink()
    (base / "cpu9/topology/core_id").unlink()
    cores = select_core_control(tmp_path)
    assert cores.max_cores is None
    # Offline siblings are usable only when explicitly named by a topology file.
    put(base / "cpu24/topology/core_cpus_list", "8,24")
    with cores.transaction():
        assert cores.max_cores is None
    (base / "cpu24/topology/core_cpus_list").unlink()
    put(base / "cpu25/topology/core_cpus_list", "9,25")
    with cores.transaction():
        assert cores.max_cores == 16
        assert cores.active() == 8
    assert cores._online(8) == 0 and cores._online(9) == 0


def test_partial_smt_enable_restores_previous_mask_and_ownership(tmp_path, monkeypatch):
    base = tree(tmp_path)
    cores = select_core_control(tmp_path)
    ctrl = coordinator(cores)
    def kernel_write(path, value):
        path = Path(path)
        path.write_text(str(value))
        if path.name == "control":
            if value == "on":
                put(base / "cpu16/online", 1)
                return False
            for i in range(16, 32):
                put(base / f"cpu{i}/online", 0)
        return True

    monkeypatch.setattr("cpu.gpd_win5.write_str", kernel_write)
    assert ctrl.apply({**PROFILE, "smt": False, "_manual_topology": "smt"}, 1).ok
    result = ctrl.apply({**PROFILE, "_manual_topology": "smt"}, 2)
    assert not result.ok and result.rollback["ok"]
    assert (base / "smt/control").read_text() == "off"
    assert all(cores._online(i) == 0 for i in range(16, 32))
    with cores.transaction():
        assert cores.state["smt_offline"] == list(range(16, 32))
        assert not cores.state.get("owned") and not cores.state.get("failed")


def test_unacknowledged_smt_write_does_not_claim_external_mask(tmp_path, monkeypatch):
    base = tree(tmp_path)
    cores = select_core_control(tmp_path)
    with cores.transaction():
        cores.state["pending"] = {"index": "smt", "before": [], "after": "off", "siblings": list(range(16, 32))}
        cores._save()
    put(base / "smt/control", "off")
    mask(base, "0-15")
    calls = []
    monkeypatch.setattr("cpu.gpd_win5.write_str", lambda *args: calls.append(args))
    reloaded = select_core_control(tmp_path)
    with reloaded.transaction():
        assert reloaded.state["smt_uncertain"] and not reloaded.state.get("smt_offline")
        assert not reloaded.release()
    assert not calls
