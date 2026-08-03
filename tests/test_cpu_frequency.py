import os
import shutil

import cpu.frequency as frequency_module
from cpu.frequency import NullCpuFrequency, select_cpu_frequency


def _write(root, rel, value):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(str(value))
    return path


def _policy(
    root,
    number,
    *,
    hw_min=400_000,
    hw_max=3_500_000,
    current_min=None,
    current_max=None,
    driver="amd-pstate-epp",
    cpus="0-3",
    affected_cpus=None,
):
    base = f"sys/devices/system/cpu/cpufreq/policy{number}"
    _write(root, f"{base}/cpuinfo_min_freq", hw_min)
    _write(root, f"{base}/cpuinfo_max_freq", hw_max)
    _write(root, f"{base}/scaling_min_freq", current_min if current_min is not None else hw_min)
    _write(root, f"{base}/scaling_max_freq", current_max if current_max is not None else hw_max)
    _write(root, f"{base}/scaling_driver", driver)
    _write(root, f"{base}/related_cpus", cpus)
    _write(root, f"{base}/affected_cpus", affected_cpus or cpus)
    return base


def test_discovers_non_contiguous_policies_with_heterogeneous_bounds(tmp_path):
    _policy(str(tmp_path), 4, hw_min=800_000, hw_max=2_800_000, driver="intel_pstate", cpus="4-7")
    _policy(str(tmp_path), 0, hw_min=400_000, hw_max=3_500_000, cpus="0-3")

    control = select_cpu_frequency(root=str(tmp_path))

    assert control.supported is True
    assert control.get_range() == (400_000, 3_500_000)
    diagnostics = control.diagnostics()
    assert diagnostics["policies"] == ["policy0", "policy4"]
    assert diagnostics["drivers"] == ["amd-pstate-epp", "intel_pstate"]
    assert diagnostics["policy_state"] == [
        {
            "name": "policy0",
            "cpus": [0, 1, 2, 3],
            "related_cpus": [0, 1, 2, 3],
            "affected_cpus": [0, 1, 2, 3],
            "driver": "amd-pstate-epp",
            "hardware_min_khz": 400_000,
            "hardware_max_khz": 3_500_000,
            "applied_min_khz": 400_000,
            "applied_max_khz": 3_500_000,
        },
        {
            "name": "policy4",
            "cpus": [4, 5, 6, 7],
            "related_cpus": [4, 5, 6, 7],
            "affected_cpus": [4, 5, 6, 7],
            "driver": "intel_pstate",
            "hardware_min_khz": 800_000,
            "hardware_max_khz": 2_800_000,
            "applied_min_khz": 800_000,
            "applied_max_khz": 2_800_000,
        },
    ]


def test_discovery_does_not_write_to_sysfs(tmp_path, monkeypatch):
    _policy(str(tmp_path), 0)
    writes = []
    monkeypatch.setattr("cpu.frequency.write_str", lambda path, value: writes.append((path, value)))

    control = select_cpu_frequency(root=str(tmp_path))

    assert control.supported is True
    assert writes == []


def test_incomplete_policy_makes_complete_set_unsupported(tmp_path):
    _policy(str(tmp_path), 0)
    base = _policy(str(tmp_path), 4)
    os.unlink(os.path.join(str(tmp_path), base, "scaling_max_freq"))

    control = select_cpu_frequency(root=str(tmp_path))

    assert isinstance(control, NullCpuFrequency)
    assert control.supported is False
    assert control.diagnostics()["reason"] == "incomplete_policy"


def test_unwritable_policy_makes_complete_set_unsupported_without_probe_write(tmp_path, monkeypatch):
    _policy(str(tmp_path), 0)
    _policy(str(tmp_path), 4, cpus="4-7")
    real_access = frequency_module.os.access
    writes = []

    def deny_second_policy_min(path, mode):
        if "policy4" in path and path.endswith("scaling_min_freq"):
            return False
        return real_access(path, mode)

    monkeypatch.setattr(frequency_module.os, "access", deny_second_policy_min)
    monkeypatch.setattr(frequency_module, "write_str", lambda path, value: writes.append((path, value)))

    control = select_cpu_frequency(root=str(tmp_path))

    assert control.supported is False
    assert control.diagnostics()["reason"] == "unwritable_policy"
    assert writes == []


def test_malformed_or_inverted_policy_bounds_are_unsupported(tmp_path):
    base = _policy(str(tmp_path), 0)
    _write(str(tmp_path), f"{base}/cpuinfo_min_freq", "not-a-number")
    assert select_cpu_frequency(root=str(tmp_path)).supported is False

    _write(str(tmp_path), f"{base}/cpuinfo_min_freq", 3_600_000)
    assert select_cpu_frequency(root=str(tmp_path)).supported is False


def test_absent_cpufreq_is_unsupported_without_writes(tmp_path, monkeypatch):
    writes = []
    monkeypatch.setattr("cpu.frequency.write_str", lambda path, value: writes.append((path, value)))

    control = select_cpu_frequency(root=str(tmp_path))

    assert isinstance(control, NullCpuFrequency)
    assert control.diagnostics()["reason"] == "no_policies"
    assert writes == []


def _read(root, rel):
    with open(os.path.join(root, rel)) as handle:
        return int(handle.read().strip())


def test_heterogeneous_policies_clamp_independently(tmp_path):
    _policy(str(tmp_path), 0, hw_min=400_000, hw_max=3_500_000)
    _policy(str(tmp_path), 4, hw_min=800_000, hw_max=2_800_000, cpus="4-7")
    control = select_cpu_frequency(root=str(tmp_path))

    result = control.set_window(500_000, 3_200_000)

    assert result.ok is True
    assert result.status == "clamped"
    assert result.requested == (500_000, 3_200_000)
    assert result.applied == (500_000, 3_200_000)
    assert control.diagnostics()["policy_state"] == [
        {
            "name": "policy0",
            "cpus": [0, 1, 2, 3],
            "related_cpus": [0, 1, 2, 3],
            "affected_cpus": [0, 1, 2, 3],
            "driver": "amd-pstate-epp",
            "hardware_min_khz": 400_000,
            "hardware_max_khz": 3_500_000,
            "applied_min_khz": 500_000,
            "applied_max_khz": 3_200_000,
        },
        {
            "name": "policy4",
            "cpus": [4, 5, 6, 7],
            "related_cpus": [4, 5, 6, 7],
            "affected_cpus": [4, 5, 6, 7],
            "driver": "amd-pstate-epp",
            "hardware_min_khz": 800_000,
            "hardware_max_khz": 2_800_000,
            "applied_min_khz": 800_000,
            "applied_max_khz": 2_800_000,
        },
    ]


def test_raising_window_writes_max_before_min(tmp_path, monkeypatch):
    base = _policy(
        str(tmp_path), 0, current_min=400_000, current_max=1_000_000
    )
    writes = []
    real_write = frequency_module.write_str

    def recording_write(path, value):
        writes.append((os.path.basename(path), int(value)))
        return real_write(path, value)

    monkeypatch.setattr(frequency_module, "write_str", recording_write)
    result = select_cpu_frequency(root=str(tmp_path)).set_window(1_200_000, 2_400_000)

    assert result.ok is True
    assert writes == [
        ("scaling_max_freq", 2_400_000),
        ("scaling_min_freq", 1_200_000),
    ]
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 1_200_000


def test_lowering_window_writes_min_before_max(tmp_path, monkeypatch):
    _policy(str(tmp_path), 0, current_min=2_600_000, current_max=3_500_000)
    writes = []
    real_write = frequency_module.write_str

    def recording_write(path, value):
        writes.append((os.path.basename(path), int(value)))
        return real_write(path, value)

    monkeypatch.setattr(frequency_module, "write_str", recording_write)
    result = select_cpu_frequency(root=str(tmp_path)).set_window(1_200_000, 2_400_000)

    assert result.ok is True
    assert writes == [
        ("scaling_min_freq", 1_200_000),
        ("scaling_max_freq", 2_400_000),
    ]


def test_sysfs_payload_ends_with_newline_for_strict_cpufreq_driver(tmp_path, monkeypatch):
    base = _policy(str(tmp_path), 0)
    real_write = frequency_module.write_str

    def strict_sysfs_write(path, value):
        if not str(value).endswith("\n"):
            return True
        return real_write(path, value)

    monkeypatch.setattr(frequency_module, "write_str", strict_sysfs_write)

    result = select_cpu_frequency(root=str(tmp_path)).set_window(1_200_000, 2_400_000)

    assert result.ok is True
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 1_200_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 2_400_000


def test_rejects_window_outside_global_envelope_without_writes(tmp_path, monkeypatch):
    _policy(str(tmp_path), 0)
    writes = []
    monkeypatch.setattr(frequency_module, "write_str", lambda path, value: writes.append((path, value)))
    control = select_cpu_frequency(root=str(tmp_path))

    below = control.set_window(300_000, 2_400_000)
    above = control.set_window(800_000, 3_600_000)
    crossed = control.set_window(2_400_000, 1_200_000)

    assert [below.status, above.status, crossed.status] == ["rejected"] * 3
    assert [below.reason, above.reason, crossed.reason] == ["invalid_range"] * 3
    assert writes == []


def test_readback_mismatch_rolls_back_original_window(tmp_path, monkeypatch):
    base = _policy(str(tmp_path), 0)
    real_write = frequency_module.write_str

    def ignore_target_min(path, value):
        if os.path.basename(path) == "scaling_min_freq" and int(value) == 1_200_000:
            return True
        return real_write(path, value)

    monkeypatch.setattr(frequency_module, "write_str", ignore_target_min)
    result = select_cpu_frequency(root=str(tmp_path)).set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.status == "failed"
    assert result.reason == "readback_mismatch"
    assert result.rollback == {"attempted": True, "ok": True}
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 400_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 3_500_000


def test_transient_readback_mismatch_retries_pair_once(tmp_path, monkeypatch):
    base = _policy(str(tmp_path), 0)
    real_write = frequency_module.write_str
    ignored = False
    delays = []

    def ignore_first_target_min(path, value):
        nonlocal ignored
        if (
            not ignored
            and os.path.basename(path) == "scaling_min_freq"
            and int(value) == 1_200_000
        ):
            ignored = True
            return True
        return real_write(path, value)

    monkeypatch.setattr(frequency_module, "write_str", ignore_first_target_min)
    monkeypatch.setattr(frequency_module.time, "sleep", delays.append)

    result = select_cpu_frequency(root=str(tmp_path)).set_window(1_200_000, 2_400_000)

    assert result.ok is True
    assert delays == [0.05]
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 1_200_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 2_400_000


def test_second_policy_failure_rolls_back_every_touched_policy(tmp_path, monkeypatch):
    _policy(str(tmp_path), 0)
    _policy(str(tmp_path), 4, cpus="4-7")
    real_write = frequency_module.write_str

    def fail_second_max(path, value):
        if "policy4" in path and os.path.basename(path) == "scaling_max_freq" and int(value) == 2_400_000:
            return False
        return real_write(path, value)

    monkeypatch.setattr(frequency_module, "write_str", fail_second_max)
    control = select_cpu_frequency(root=str(tmp_path))
    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "write_failed"
    assert result.rollback == {"attempted": True, "ok": True}
    assert control.get_window() == (400_000, 3_500_000)


def test_failed_rollback_is_reported_as_partial(tmp_path, monkeypatch):
    _policy(str(tmp_path), 0)
    _policy(str(tmp_path), 4, cpus="4-7")
    real_write = frequency_module.write_str

    def fail_apply_and_rollback(path, value):
        value = int(value)
        if "policy4" in path and os.path.basename(path) == "scaling_max_freq" and value == 2_400_000:
            return False
        if "policy0" in path and os.path.basename(path) == "scaling_min_freq" and value == 400_000:
            return False
        return real_write(path, value)

    monkeypatch.setattr(frequency_module, "write_str", fail_apply_and_rollback)
    result = select_cpu_frequency(root=str(tmp_path)).set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.status == "partial"
    assert result.rollback == {"attempted": True, "ok": False}


def test_auto_restores_session_baseline_once_then_becomes_unverifiable(tmp_path, monkeypatch):
    _policy(str(tmp_path), 0, current_min=600_000, current_max=3_000_000)
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True

    restored = control.set_auto()

    assert restored.ok is True
    assert restored.status == "restored"
    assert control.get_window() == (600_000, 3_000_000)
    writes = []
    monkeypatch.setattr(frequency_module, "write_str", lambda path, value: writes.append((path, value)))
    second = control.set_auto()
    assert second.ok is False
    assert second.status == "unverifiable"
    assert writes == []


def test_emergency_auto_keeps_baseline_for_a_late_manual_write(tmp_path):
    base = _policy(
        str(tmp_path), 0, current_min=600_000, current_max=3_000_000
    )
    durable = {"value": None}
    control = select_cpu_frequency(
        root=str(tmp_path),
        persist_state=lambda state: durable.__setitem__("value", state),
        boot_id="boot-1",
    )
    assert control.set_window(1_200_000, 2_400_000).ok is True

    emergency = control.set_auto(preserve_ownership=True)

    assert emergency.ok is True
    assert control.get_window() == (600_000, 3_000_000)
    assert durable["value"] is not None
    _write(str(tmp_path), f"{base}/scaling_min_freq", 1_200_000)
    _write(str(tmp_path), f"{base}/scaling_max_freq", 2_400_000)

    final = control.set_auto()

    assert final.ok is True
    assert control.get_window() == (600_000, 3_000_000)
    assert durable["value"] is None


def test_restart_recovers_durable_baseline_before_manual_reapply(tmp_path):
    _policy(
        str(tmp_path), 0,
        current_min=600_000,
        current_max=3_000_000,
    )
    durable = {"value": None}

    def persist(state):
        durable["value"] = state

    first = select_cpu_frequency(
        root=str(tmp_path),
        persist_state=persist,
        boot_id="boot-1",
    )
    assert first.set_window(1_200_000, 2_400_000).ok is True
    assert durable["value"] is not None

    restarted = select_cpu_frequency(
        root=str(tmp_path),
        persisted_state=durable["value"],
        persist_state=persist,
        boot_id="boot-1",
    )
    assert restarted.diagnostics()["owned"] is True
    assert restarted.set_window(1_200_000, 2_400_000).ok is True

    restored = restarted.set_auto()

    assert restored.ok is True
    assert restarted.get_window() == (600_000, 3_000_000)
    assert durable["value"] is None


def test_manual_takeover_never_writes_without_durable_baseline(tmp_path, monkeypatch):
    _policy(str(tmp_path), 0)
    writes = []
    monkeypatch.setattr(
        frequency_module,
        "write_str",
        lambda path, value: writes.append((path, value)) or True,
    )

    def fail_persist(_state):
        raise OSError("disk full")

    control = select_cpu_frequency(
        root=str(tmp_path),
        persist_state=fail_persist,
        boot_id="boot-1",
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "ownership_persist_failed"
    assert writes == []
    assert control.diagnostics()["owned"] is False


def test_manual_takeover_fails_closed_when_boot_id_is_unreadable(
    tmp_path, monkeypatch
):
    _policy(str(tmp_path), 0)
    writes = []
    persisted = []
    monkeypatch.setattr(
        frequency_module,
        "write_str",
        lambda path, value: writes.append((path, value)) or True,
    )
    control = select_cpu_frequency(
        root=str(tmp_path),
        persist_state=persisted.append,
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "boot_id_unavailable"
    assert persisted == []
    assert writes == []


def test_identity_change_with_manual_target_keeps_handoff_pending(
    tmp_path, monkeypatch
):
    base = _policy(
        str(tmp_path), 0,
        driver="intel_pstate",
        current_min=600_000,
        current_max=3_000_000,
    )
    control = select_cpu_frequency(root=str(tmp_path))
    real_read_window = frequency_module.Policy.read_window
    changed = False

    def replace_driver_after_target_read(policy):
        nonlocal changed
        window = real_read_window(policy)
        if not changed and window == (1_200_000, 2_400_000):
            changed = True
            _write(str(tmp_path), f"{base}/scaling_driver", "intel_cpufreq")
        return window

    monkeypatch.setattr(
        frequency_module.Policy,
        "read_window",
        replace_driver_after_target_read,
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "policy_topology_changed"
    assert control.diagnostics()["owned"] is True
    assert control.set_auto().reason == "baseline_stale"
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 1_200_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 2_400_000


def test_auto_retries_transient_restore_readback_once(tmp_path, monkeypatch):
    base = _policy(str(tmp_path), 0, current_min=600_000, current_max=3_000_000)
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True
    real_write = frequency_module.write_str
    ignored = False
    delays = []

    def ignore_first_baseline_min(path, value):
        nonlocal ignored
        if (
            not ignored
            and os.path.basename(path) == "scaling_min_freq"
            and int(value) == 600_000
        ):
            ignored = True
            return True
        return real_write(path, value)

    monkeypatch.setattr(frequency_module, "write_str", ignore_first_baseline_min)
    monkeypatch.setattr(frequency_module.time, "sleep", delays.append)

    restored = control.set_auto()

    assert restored.ok is True
    assert delays == [0.05]
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 600_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 3_000_000


def test_auto_accepts_exact_readback_when_driver_reports_write_failure(
    tmp_path, monkeypatch
):
    base = _policy(
        str(tmp_path), 0, current_min=600_000, current_max=3_000_000
    )
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True
    real_write = frequency_module.write_str

    def write_but_report_failure(path, value):
        written = real_write(path, value)
        if os.path.basename(path) == "scaling_min_freq" and int(value) == 600_000:
            return False
        return written

    monkeypatch.setattr(
        frequency_module, "write_str", write_but_report_failure
    )

    restored = control.set_auto()

    assert restored.ok is True
    assert restored.status == "restored"
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 600_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 3_000_000


def test_auto_attempts_remaining_policies_after_one_restore_failure(tmp_path, monkeypatch):
    first = _policy(str(tmp_path), 0, current_min=600_000, current_max=3_000_000)
    second = _policy(
        str(tmp_path), 4, current_min=800_000, current_max=2_800_000, cpus="4-7"
    )
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True
    real_write = frequency_module.write_str

    def fail_first_policy_restore(path, value):
        if "policy0" in path and int(value) == 600_000:
            return False
        return real_write(path, value)

    monkeypatch.setattr(frequency_module, "write_str", fail_first_policy_restore)

    restored = control.set_auto()

    assert restored.ok is False
    assert restored.status == "partial"
    assert _read(str(tmp_path), f"{first}/scaling_min_freq") == 1_200_000
    assert _read(str(tmp_path), f"{second}/scaling_min_freq") == 800_000
    assert _read(str(tmp_path), f"{second}/scaling_max_freq") == 2_800_000


def test_policy_topology_change_starts_new_epoch_and_applies_current_request(tmp_path):
    _policy(str(tmp_path), 0)
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True
    first_epoch = control.diagnostics()["epoch"]
    _policy(str(tmp_path), 4, hw_min=800_000, hw_max=2_800_000, cpus="4-7")

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is True
    assert control.diagnostics()["epoch"] == first_epoch + 1
    assert [row["name"] for row in control.diagnostics()["policy_state"]] == ["policy0", "policy4"]
    assert control.get_window() == (1_200_000, 2_400_000)


def test_policy_created_during_apply_prevents_success_and_rolls_back(
    tmp_path, monkeypatch
):
    first = _policy(str(tmp_path), 0)
    control = select_cpu_frequency(root=str(tmp_path))
    real_write = frequency_module.write_str
    created = False

    def create_policy_during_first_write(path, value):
        nonlocal created
        written = real_write(path, value)
        if not created:
            created = True
            _policy(
                str(tmp_path), 4, hw_min=800_000, hw_max=2_800_000,
                cpus="4-7", driver="intel_pstate",
            )
        return written

    monkeypatch.setattr(
        frequency_module, "write_str", create_policy_during_first_write
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "policy_topology_changed"
    assert _read(str(tmp_path), f"{first}/scaling_min_freq") == 400_000
    assert _read(str(tmp_path), f"{first}/scaling_max_freq") == 3_500_000
    assert control.diagnostics()["owned"] is False


def test_affected_cpu_change_during_apply_prevents_success_and_rolls_back(
    tmp_path, monkeypatch
):
    base = _policy(str(tmp_path), 0, cpus="0-3", affected_cpus="0-3")
    control = select_cpu_frequency(root=str(tmp_path))
    real_write = frequency_module.write_str
    changed = False

    def offline_cpu_during_first_write(path, value):
        nonlocal changed
        written = real_write(path, value)
        if not changed:
            changed = True
            _write(str(tmp_path), f"{base}/affected_cpus", "0-2")
        return written

    monkeypatch.setattr(
        frequency_module, "write_str", offline_cpu_during_first_write
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "policy_topology_changed"
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 400_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 3_500_000


def test_policy_driver_change_rejects_manual_reapply_before_write(
    tmp_path, monkeypatch
):
    base = _policy(str(tmp_path), 0, driver="amd-pstate-epp")
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True
    _write(str(tmp_path), f"{base}/scaling_driver", "intel_pstate")
    writes = []
    monkeypatch.setattr(
        frequency_module, "write_str",
        lambda path, value: writes.append((path, value)),
    )

    result = control.set_window(1_500_000, 3_000_000)

    assert result.ok is False
    assert result.reason == "policy_identity_changed"
    assert writes == []


def test_replaced_policy_is_not_overwritten_by_topology_rollback(
    tmp_path, monkeypatch
):
    base = _policy(str(tmp_path), 0, driver="amd-pstate-epp")
    control = select_cpu_frequency(root=str(tmp_path))
    original_read = frequency_module.Policy.read_window
    reads = 0

    def replace_after_apply_readback(policy):
        nonlocal reads
        reads += 1
        value = original_read(policy)
        if reads == 2:
            _write(str(tmp_path), f"{base}/scaling_driver", "amd-pstate")
            _write(str(tmp_path), f"{base}/scaling_min_freq", 700_000)
            _write(str(tmp_path), f"{base}/scaling_max_freq", 3_000_000)
        return value

    monkeypatch.setattr(
        frequency_module.Policy, "read_window", replace_after_apply_readback
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "policy_topology_changed"
    assert result.rollback == {"attempted": True, "ok": False}
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 700_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 3_000_000


def test_final_external_window_drift_is_never_reported_as_applied(
    tmp_path, monkeypatch
):
    base = _policy(str(tmp_path), 0)
    control = select_cpu_frequency(root=str(tmp_path))
    original_read = frequency_module.Policy.read_window
    reads = 0

    def drift_on_final_read(policy):
        nonlocal reads
        reads += 1
        if reads == 3:
            _write(str(tmp_path), f"{base}/scaling_min_freq", 700_000)
            _write(str(tmp_path), f"{base}/scaling_max_freq", 3_000_000)
        return original_read(policy)

    monkeypatch.setattr(
        frequency_module.Policy, "read_window", drift_on_final_read
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "readback_mismatch"
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 700_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 3_000_000


def test_policy_created_during_final_readback_is_never_omitted_from_success(
    tmp_path, monkeypatch
):
    first = _policy(str(tmp_path), 0)
    control = select_cpu_frequency(root=str(tmp_path))
    original_read = frequency_module.Policy.read_window
    reads = 0

    def add_policy_during_final_read(policy):
        nonlocal reads
        reads += 1
        value = original_read(policy)
        if reads == 3:
            _policy(
                str(tmp_path), 4, hw_min=800_000, hw_max=2_800_000,
                cpus="4-7", driver="intel_pstate",
            )
        return value

    monkeypatch.setattr(
        frequency_module.Policy, "read_window", add_policy_during_final_read
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "policy_topology_changed"
    assert _read(str(tmp_path), f"{first}/scaling_min_freq") == 400_000
    assert _read(str(tmp_path), f"{first}/scaling_max_freq") == 3_500_000


def test_auto_does_not_restore_baseline_through_a_replaced_driver(
    tmp_path, monkeypatch
):
    base = _policy(
        str(tmp_path), 0, driver="intel_pstate",
        current_min=600_000, current_max=3_000_000,
    )
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True
    original_read = frequency_module.Policy.read_window
    replaced = False

    def replace_during_restore_read(policy):
        nonlocal replaced
        value = original_read(policy)
        if not replaced:
            replaced = True
            _write(str(tmp_path), f"{base}/scaling_driver", "intel_cpufreq")
            _write(str(tmp_path), f"{base}/scaling_min_freq", 700_000)
            _write(str(tmp_path), f"{base}/scaling_max_freq", 2_900_000)
        return value

    monkeypatch.setattr(
        frequency_module.Policy, "read_window", replace_during_restore_read
    )

    result = control.set_auto()

    assert result.ok is False
    assert control.diagnostics()["owned"] is True
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 700_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 2_900_000


def test_driver_replacement_during_apply_is_never_rolled_back_through_old_policy(
    tmp_path, monkeypatch
):
    base = _policy(str(tmp_path), 0, driver="amd-pstate-epp")
    control = select_cpu_frequency(root=str(tmp_path))
    real_read_window = frequency_module.Policy.read_window
    reads = 0

    def replace_after_apply_readback(policy):
        nonlocal reads
        reads += 1
        value = real_read_window(policy)
        if reads == 2:
            _write(str(tmp_path), f"{base}/scaling_driver", "amd-pstate")
            _write(str(tmp_path), f"{base}/scaling_min_freq", 700_000)
            _write(str(tmp_path), f"{base}/scaling_max_freq", 3_000_000)
        return value

    monkeypatch.setattr(
        frequency_module.Policy, "read_window", replace_after_apply_readback
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "policy_topology_changed"
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 700_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 3_000_000


def test_final_window_drift_cannot_be_reported_as_applied(tmp_path, monkeypatch):
    base = _policy(str(tmp_path), 0)
    control = select_cpu_frequency(root=str(tmp_path))
    real_read_window = frequency_module.Policy.read_window
    reads = 0

    def drift_at_final_readback(policy):
        nonlocal reads
        reads += 1
        if reads == 3:
            _write(str(tmp_path), f"{base}/scaling_min_freq", 700_000)
            _write(str(tmp_path), f"{base}/scaling_max_freq", 3_000_000)
        return real_read_window(policy)

    monkeypatch.setattr(
        frequency_module.Policy, "read_window", drift_at_final_readback
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "readback_mismatch"
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 700_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 3_000_000


def test_final_drift_restores_only_policies_that_still_hold_plugin_target(
    tmp_path, monkeypatch
):
    first = _policy(str(tmp_path), 0)
    second = _policy(str(tmp_path), 4, cpus="4-7")
    control = select_cpu_frequency(root=str(tmp_path))
    real_read_window = frequency_module.Policy.read_window
    reads = {"policy0": 0, "policy4": 0}

    def drift_second_policy_at_final_readback(policy):
        reads[policy.name] += 1
        if policy.name == "policy4" and reads[policy.name] == 3:
            _write(str(tmp_path), f"{second}/scaling_min_freq", 900_000)
            _write(str(tmp_path), f"{second}/scaling_max_freq", 2_700_000)
        return real_read_window(policy)

    monkeypatch.setattr(
        frequency_module.Policy,
        "read_window",
        drift_second_policy_at_final_readback,
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "readback_mismatch"
    assert _read(str(tmp_path), f"{first}/scaling_min_freq") == 400_000
    assert _read(str(tmp_path), f"{first}/scaling_max_freq") == 3_500_000
    assert _read(str(tmp_path), f"{second}/scaling_min_freq") == 900_000
    assert _read(str(tmp_path), f"{second}/scaling_max_freq") == 2_700_000
    assert control.diagnostics()["owned"] is False


def test_policy_created_during_final_readback_cannot_be_omitted_from_success(
    tmp_path, monkeypatch
):
    _policy(str(tmp_path), 0)
    control = select_cpu_frequency(root=str(tmp_path))
    real_read_window = frequency_module.Policy.read_window
    reads = 0

    def create_policy_at_final_readback(policy):
        nonlocal reads
        reads += 1
        value = real_read_window(policy)
        if reads == 3:
            _policy(
                str(tmp_path), 4, hw_min=800_000, hw_max=2_800_000,
                cpus="4-7", driver="intel_pstate",
            )
        return value

    monkeypatch.setattr(
        frequency_module.Policy, "read_window", create_policy_at_final_readback
    )

    result = control.set_window(1_200_000, 2_400_000)

    assert result.ok is False
    assert result.reason == "policy_topology_changed"


def test_auto_never_restores_baseline_through_a_replaced_driver(
    tmp_path, monkeypatch
):
    base = _policy(
        str(tmp_path), 0, driver="intel_pstate",
        current_min=600_000, current_max=3_000_000,
    )
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True
    real_read_window = frequency_module.Policy.read_window
    replaced = False

    def replace_at_restore_read(policy):
        nonlocal replaced
        value = real_read_window(policy)
        if not replaced:
            replaced = True
            _write(str(tmp_path), f"{base}/scaling_driver", "intel_cpufreq")
            _write(str(tmp_path), f"{base}/scaling_min_freq", 700_000)
            _write(str(tmp_path), f"{base}/scaling_max_freq", 2_900_000)
        return value

    monkeypatch.setattr(
        frequency_module.Policy, "read_window", replace_at_restore_read
    )

    result = control.set_auto()

    assert result.ok is False
    assert result.status == "partial"
    assert control.diagnostics()["owned"] is True
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 700_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 2_900_000


def test_auto_keeps_baseline_across_temporary_policy_topology_change(tmp_path):
    first = _policy(
        str(tmp_path), 0, current_min=600_000, current_max=3_000_000
    )
    second = _policy(
        str(tmp_path), 4, current_min=800_000, current_max=2_800_000,
        cpus="4-7",
    )
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True

    shutil.rmtree(os.path.join(str(tmp_path), second))
    diagnostics = control.diagnostics()

    assert diagnostics["owned"] is True
    assert diagnostics["requested"] == [1_200_000, 2_400_000]

    _policy(
        str(tmp_path), 4, current_min=1_200_000, current_max=2_400_000,
        cpus="4-7",
    )
    restored = control.set_auto()

    assert restored.ok is True
    assert _read(str(tmp_path), f"{first}/scaling_min_freq") == 600_000
    assert _read(str(tmp_path), f"{first}/scaling_max_freq") == 3_000_000
    assert _read(str(tmp_path), f"{second}/scaling_min_freq") == 800_000
    assert _read(str(tmp_path), f"{second}/scaling_max_freq") == 2_800_000


def test_auto_restores_matching_policies_when_one_policy_stays_offline(tmp_path):
    first = _policy(
        str(tmp_path), 0, current_min=600_000, current_max=3_000_000
    )
    second = _policy(
        str(tmp_path), 4, current_min=800_000, current_max=2_800_000,
        cpus="4-7",
    )
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True

    shutil.rmtree(os.path.join(str(tmp_path), second))
    restored = control.set_auto()

    assert restored.ok is False
    assert restored.status == "partial"
    assert restored.reason == "baseline_stale"
    assert _read(str(tmp_path), f"{first}/scaling_min_freq") == 600_000
    assert _read(str(tmp_path), f"{first}/scaling_max_freq") == 3_000_000
    assert control.diagnostics()["owned"] is True


def test_partial_auto_attempts_every_matching_policy_after_restore_failure(
    tmp_path, monkeypatch
):
    first = _policy(
        str(tmp_path), 0, current_min=600_000, current_max=3_000_000
    )
    missing = _policy(
        str(tmp_path), 4, current_min=800_000, current_max=2_800_000,
        cpus="4-7",
    )
    last = _policy(
        str(tmp_path), 8, current_min=700_000, current_max=2_900_000,
        cpus="8-11",
    )
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True
    shutil.rmtree(os.path.join(str(tmp_path), missing))
    real_write = frequency_module.write_str

    def fail_first_policy_restore(path, value):
        if "policy0" in path and int(value) == 600_000:
            return False
        return real_write(path, value)

    monkeypatch.setattr(frequency_module, "write_str", fail_first_policy_restore)

    restored = control.set_auto()

    assert restored.ok is False
    assert restored.status == "partial"
    assert restored.reason == "restore_failed"
    assert _read(str(tmp_path), f"{first}/scaling_min_freq") == 1_200_000
    assert _read(str(tmp_path), f"{last}/scaling_min_freq") == 700_000
    assert _read(str(tmp_path), f"{last}/scaling_max_freq") == 2_900_000


def test_auto_rejects_replacement_policy_that_reuses_previous_name(tmp_path):
    base = _policy(
        str(tmp_path), 0, current_min=600_000, current_max=3_000_000,
        cpus="0-3",
    )
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True

    shutil.rmtree(os.path.join(str(tmp_path), base))
    _policy(
        str(tmp_path), 0, current_min=500_000, current_max=3_200_000,
        cpus="4-7",
    )

    restored = control.set_auto()

    assert restored.ok is False
    assert restored.status == "unverifiable"
    assert restored.reason == "baseline_stale"
    assert _read(str(tmp_path), f"{base}/scaling_min_freq") == 500_000
    assert _read(str(tmp_path), f"{base}/scaling_max_freq") == 3_200_000


def test_manual_reapply_rejects_replacement_policy_before_any_write(
    tmp_path, monkeypatch
):
    base = _policy(
        str(tmp_path), 0, current_min=600_000, current_max=3_000_000,
        cpus="0-3",
    )
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True

    shutil.rmtree(os.path.join(str(tmp_path), base))
    _policy(
        str(tmp_path), 0, current_min=500_000, current_max=3_200_000,
        cpus="4-7",
    )
    writes = []
    monkeypatch.setattr(
        frequency_module, "write_str",
        lambda path, value: writes.append((path, value)),
    )

    reapplied = control.set_window(1_500_000, 3_000_000)

    assert reapplied.ok is False
    assert reapplied.status == "rejected"
    assert reapplied.reason == "policy_identity_changed"
    assert writes == []
