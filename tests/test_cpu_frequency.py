import os

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
):
    base = f"sys/devices/system/cpu/cpufreq/policy{number}"
    _write(root, f"{base}/cpuinfo_min_freq", hw_min)
    _write(root, f"{base}/cpuinfo_max_freq", hw_max)
    _write(root, f"{base}/scaling_min_freq", current_min if current_min is not None else hw_min)
    _write(root, f"{base}/scaling_max_freq", current_max if current_max is not None else hw_max)
    _write(root, f"{base}/scaling_driver", driver)
    _write(root, f"{base}/related_cpus", cpus)
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
            "driver": "amd-pstate-epp",
            "hardware_min_khz": 400_000,
            "hardware_max_khz": 3_500_000,
            "applied_min_khz": 400_000,
            "applied_max_khz": 3_500_000,
        },
        {
            "name": "policy4",
            "cpus": [4, 5, 6, 7],
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
            "driver": "amd-pstate-epp",
            "hardware_min_khz": 400_000,
            "hardware_max_khz": 3_500_000,
            "applied_min_khz": 500_000,
            "applied_max_khz": 3_200_000,
        },
        {
            "name": "policy4",
            "cpus": [4, 5, 6, 7],
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

    result = select_cpu_frequency(root=str(tmp_path)).set_window(1_200_000, 2_400_000)

    assert result.ok is True
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


def test_auto_retries_transient_restore_readback_once(tmp_path, monkeypatch):
    base = _policy(str(tmp_path), 0, current_min=600_000, current_max=3_000_000)
    control = select_cpu_frequency(root=str(tmp_path))
    assert control.set_window(1_200_000, 2_400_000).ok is True
    real_write = frequency_module.write_str
    ignored = False

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

    restored = control.set_auto()

    assert restored.ok is True
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
