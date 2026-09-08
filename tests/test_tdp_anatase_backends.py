import os

from tdp.amd_dptc import AmdDptcBackend
from tdp.asus_nb_wmi import AsusNbWmiBackend
from tdp.backend import NullBackend
from tdp.firmware_attr import FirmwareAttrBackend
from tdp.msi_claw_a8 import MsiClawA8FirmwareBackend
from tdp.types import TdpLimits


LIMITS = TdpLimits(min_w=7, default_w=15, max_w=25, max_ac_w=30)
RAILS = {
    "pl1": "ppt_pl1_spl",
    "pl2": "ppt_pl2_sppt",
    "pl3": "ppt_pl3_fppt",
}


def _write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(str(value))


def _read(path):
    with open(path) as handle:
        return handle.read().strip()


def _legacy_path(root, rail):
    leaf = "ppt_fppt" if rail == "pl3" else RAILS[rail]
    return os.path.join(root, "sys/devices/platform/asus-nb-wmi", leaf)


def _mk_asus_legacy(root, values=None):
    values = values or {"pl1": 15, "pl2": 20, "pl3": 25}
    for rail, value in values.items():
        _write(_legacy_path(root, rail), value)


def _fw_path(root, provider, rail, leaf="current_value"):
    return os.path.join(
        root,
        "sys/class/firmware-attributes",
        provider,
        "attributes",
        RAILS[rail],
        leaf,
    )


def _mk_firmware(root, provider, values=None):
    values = values or {"pl1": 15, "pl2": 20, "pl3": 25}
    maximums = {"pl1": 35, "pl2": 45, "pl3": 55}
    for rail, value in values.items():
        _write(_fw_path(root, provider, rail), value)
        _write(_fw_path(root, provider, rail, "min_value"), 5)
        _write(_fw_path(root, provider, rail, "max_value"), maximums[rail])


def _mk_profile(root, provider="amd-dptc", profile="balanced", include_custom=True):
    base = os.path.join(root, "sys/class/platform-profile/platform-profile-0")
    _write(os.path.join(base, "name"), provider)
    _write(os.path.join(base, "profile"), profile)
    choices = "low-power balanced performance"
    if include_custom:
        choices += " custom"
    _write(os.path.join(base, "choices"), choices)
    return os.path.join(base, "profile")


def _mk_dmi(root, board_name):
    _write(os.path.join(root, "sys/class/dmi/id/board_name"), board_name)


def test_backend_contract_has_safe_default_release():
    assert NullBackend("absent").release() is True


def _anatase_asus_backend(root):
    return FirmwareAttrBackend(
        "asus-armoury",
        LIMITS,
        root=root,
        safety_lock_path=os.path.join(root, "run/pdc/asus-transaction.lock"),
        restore_on_release=True,
        ownership_lock_path=os.path.join(root, "run/pdc/asus-ownership.lock"),
    )


def test_anatase_asus_armoury_releases_both_surfaces_exactly(tmp_path):
    root = str(tmp_path)
    primary = {"pl1": 15, "pl2": 20, "pl3": 25}
    legacy = {"pl1": 5, "pl2": 5, "pl3": 5}
    _mk_firmware(root, "asus-armoury", primary)
    _mk_asus_legacy(root, legacy)
    backend = _anatase_asus_backend(root)

    result = backend.set_levels(10, 12, 14, ac=True)

    assert result.ok is True
    assert backend.release() is True
    assert {
        rail: int(_read(_fw_path(root, "asus-armoury", rail)))
        for rail in RAILS
    } == primary
    assert {
        rail: int(_read(_legacy_path(root, rail)))
        for rail in RAILS
    } == legacy


def test_anatase_asus_armoury_recovers_owned_surfaces_after_restart(tmp_path):
    root = str(tmp_path)
    primary = {"pl1": 15, "pl2": 20, "pl3": 25}
    legacy = {"pl1": 5, "pl2": 5, "pl3": 5}
    _mk_firmware(root, "asus-armoury", primary)
    _mk_asus_legacy(root, legacy)

    first = _anatase_asus_backend(root)
    assert first.set_levels(10, 12, 14, ac=True).ok is True

    restarted = _anatase_asus_backend(root)
    assert restarted.safety_locked is True
    blocked = restarted.set_levels(11, 13, 15, ac=True)
    assert blocked.ok is False
    assert blocked.detail == "firmware ownership recovery pending"
    assert restarted.recover_runtime_transaction()["ok"] is True
    assert {
        rail: int(_read(_fw_path(root, "asus-armoury", rail)))
        for rail in RAILS
    } == primary
    assert {
        rail: int(_read(_legacy_path(root, rail)))
        for rail in RAILS
    } == legacy


def test_anatase_asus_relinquishes_stale_ownership_without_sysfs_writes(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    _mk_firmware(root, "asus-armoury")
    _mk_asus_legacy(root)
    first = _anatase_asus_backend(root)
    assert first.set_levels(10, 15, 15, ac=True).ok is True
    hhd_values = {"pl1": 18, "pl2": 23, "pl3": 29}
    for rail, value in hhd_values.items():
        _write(_fw_path(root, "asus-armoury", rail), value)
        _write(_legacy_path(root, rail), value)

    restarted = _anatase_asus_backend(root)
    monkeypatch.setattr(
        restarted,
        "_write",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected write")),
    )

    assert restarted.relinquish_ownership()["ok"] is True
    assert restarted.safety_locked is False
    assert {
        rail: int(_read(_fw_path(root, "asus-armoury", rail)))
        for rail in RAILS
    } == hhd_values
    assert {
        rail: int(_read(_legacy_path(root, rail)))
        for rail in RAILS
    } == hhd_values


def test_anatase_asus_does_not_relinquish_ownership_during_partial_transaction(
    tmp_path,
):
    root = str(tmp_path)
    _mk_firmware(root, "asus-armoury")
    _mk_asus_legacy(root)
    first = _anatase_asus_backend(root)
    assert first.set_levels(10, 15, 15, ac=True).ok is True
    first._runtime_lock_payload = {"state": "write_pending"}
    first._write_circuit_open = "write_pending"

    result = first.relinquish_ownership()

    assert result == {
        "ok": False,
        "detail": "firmware transaction recovery pending",
    }
    assert first.safety_locked is True


def test_anatase_asus_release_drains_transaction_before_ownership(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    primary = {"pl1": 15, "pl2": 20, "pl3": 25}
    legacy = {"pl1": 5, "pl2": 5, "pl3": 5}
    _mk_firmware(root, "asus-armoury", primary)
    _mk_asus_legacy(root, legacy)
    backend = _anatase_asus_backend(root)
    transaction_path = os.path.join(root, "run/pdc/asus-transaction.lock")
    ownership_path = os.path.join(root, "run/pdc/asus-ownership.lock")
    clear = backend._safety_lock.clear
    monkeypatch.setattr(backend._safety_lock, "clear", lambda: False)

    result = backend.set_levels(10, 12, 14, ac=True)

    assert result.ok is False
    assert os.path.exists(transaction_path)
    assert os.path.exists(ownership_path)
    monkeypatch.setattr(backend._safety_lock, "clear", clear)
    assert backend.release() is True
    assert not os.path.exists(transaction_path)
    assert not os.path.exists(ownership_path)
    assert {
        rail: int(_read(_fw_path(root, "asus-armoury", rail)))
        for rail in RAILS
    } == primary
    assert {
        rail: int(_read(_legacy_path(root, rail)))
        for rail in RAILS
    } == legacy


def test_asus_legacy_requires_pl1_and_uses_only_present_rails(tmp_path):
    root = str(tmp_path)
    backend = AsusNbWmiBackend(LIMITS, root=root)
    assert backend.supported is False

    _write(_legacy_path(root, "pl1"), 15)
    backend = AsusNbWmiBackend(LIMITS, root=root)

    assert backend.supported is True
    assert backend.supports_levels is False
    assert backend.observe().as_dict()["surfaces"] == {
        "asus-nb-wmi": {
            "pl1": {"applied": 15, "min": 7, "max": 30},
        }
    }


def test_asus_legacy_writes_highest_rail_first_and_releases_snapshot(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_asus_legacy(root, original)
    backend = AsusNbWmiBackend(LIMITS, root=root)
    writes = []
    real_write = backend._write

    def record(path, value):
        writes.append((os.path.basename(path), value))
        return real_write(path, value)

    monkeypatch.setattr(backend, "_write", record)

    result = backend.set_levels(10, 12, 14, ac=True)

    assert result.ok is True
    assert [name for name, _value in writes] == [
        "ppt_fppt",
        "ppt_pl2_sppt",
        "ppt_pl1_spl",
    ]
    assert backend.release() is True
    assert {
        rail: int(_read(_legacy_path(root, rail)))
        for rail in RAILS
    } == original


def test_asus_legacy_recovers_owned_rails_after_restart(tmp_path):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_asus_legacy(root, original)
    lock_path = os.path.join(root, "run/pdc/asus-legacy-ownership.lock")
    first = AsusNbWmiBackend(LIMITS, root=root, ownership_lock_path=lock_path)

    assert first.set_levels(10, 12, 14, ac=True).ok is True

    restarted = AsusNbWmiBackend(
        LIMITS,
        root=root,
        ownership_lock_path=lock_path,
    )
    assert restarted.safety_locked is True
    assert restarted.recover_runtime_transaction()["ok"] is True
    assert {
        rail: int(_read(_legacy_path(root, rail)))
        for rail in RAILS
    } == original


def test_asus_legacy_relinquishes_stale_ownership_without_sysfs_writes(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    _mk_asus_legacy(root)
    lock_path = os.path.join(root, "run/pdc/asus-legacy-ownership.lock")
    first = AsusNbWmiBackend(LIMITS, root=root, ownership_lock_path=lock_path)
    assert first.set_levels(10, 15, 15, ac=True).ok is True
    hhd_values = {"pl1": 18, "pl2": 23, "pl3": 29}
    for rail, value in hhd_values.items():
        _write(_legacy_path(root, rail), value)

    restarted = AsusNbWmiBackend(
        LIMITS,
        root=root,
        ownership_lock_path=lock_path,
    )
    monkeypatch.setattr(
        restarted,
        "_write",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected write")),
    )

    assert restarted.relinquish_ownership()["ok"] is True
    assert restarted.safety_locked is False
    assert {
        rail: int(_read(_legacy_path(root, rail)))
        for rail in RAILS
    } == hhd_values


def test_asus_legacy_rolls_back_every_rail_after_partial_failure(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_asus_legacy(root, original)
    backend = AsusNbWmiBackend(LIMITS, root=root)
    real_write = backend._write
    failed = False

    def fail_once(path, value):
        nonlocal failed
        if path == _legacy_path(root, "pl2") and not failed:
            failed = True
            return False
        return real_write(path, value)

    monkeypatch.setattr(backend, "_write", fail_once)

    result = backend.set_levels(10, 12, 14, ac=True)

    assert result.ok is False
    assert "rolled back" in result.detail
    assert {
        rail: int(_read(_legacy_path(root, rail)))
        for rail in RAILS
    } == original


def test_asus_legacy_attempts_all_restores_when_one_rollback_write_fails(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_asus_legacy(root, original)
    backend = AsusNbWmiBackend(LIMITS, root=root)
    real_read = backend._read_int
    real_write = backend._write
    pl1_reads = 0

    def mismatch_after_write(path):
        nonlocal pl1_reads
        if path == _legacy_path(root, "pl1"):
            pl1_reads += 1
            if pl1_reads == 2:
                return 9
        return real_read(path)

    def fail_pl2_restore(path, value):
        if path == _legacy_path(root, "pl2") and value == original["pl2"]:
            return False
        return real_write(path, value)

    monkeypatch.setattr(backend, "_read_int", mismatch_after_write)
    monkeypatch.setattr(backend, "_write", fail_pl2_restore)

    result = backend.set_levels(10, 12, 14, ac=True)

    assert result.ok is False
    assert "rollback failed" in result.detail
    assert _read(_legacy_path(root, "pl1")) == "15"
    assert _read(_legacy_path(root, "pl3")) == "25"
    writes = []
    monkeypatch.setattr(
        backend,
        "_write",
        lambda path, value: writes.append((path, value)) or real_write(path, value),
    )

    blocked = backend.set_levels(11, 13, 15, ac=True)

    assert blocked.ok is False
    assert blocked.detail == "TDP recovery pending"
    assert writes == []
    monkeypatch.setattr(backend, "_write", real_write)
    assert backend.release() is True
    assert {
        rail: int(_read(_legacy_path(root, rail)))
        for rail in RAILS
    } == original


def test_amd_dptc_requires_matching_profile_custom_and_pl1(tmp_path):
    root = str(tmp_path)
    _mk_firmware(root, "amd-dptc")
    without_profile = AmdDptcBackend(LIMITS, root=root)
    assert without_profile.supported is False

    _mk_profile(root, provider="amd-pmf")
    wrong_profile = AmdDptcBackend(LIMITS, root=root)
    assert wrong_profile.supported is False

    _mk_profile(root, include_custom=False)
    without_custom = AmdDptcBackend(LIMITS, root=root)
    assert without_custom.supported is False

    _mk_profile(root)
    backend = AmdDptcBackend(LIMITS, root=root)

    assert backend.supported is True
    assert backend.profile_choices() == [
        "low-power",
        "balanced",
        "performance",
        "custom",
    ]


def test_amd_dptc_does_not_resolve_relative_attributes_without_provider(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path / "root")
    _mk_profile(root)
    for rail in RAILS:
        _write(os.path.join(tmp_path, "attributes", RAILS[rail], "current_value"), 15)
    monkeypatch.chdir(tmp_path)

    backend = AmdDptcBackend(LIMITS, root=root)

    assert backend.supported is False


def test_amd_dptc_uses_live_bounds_and_restores_profile_and_rails(tmp_path):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_firmware(root, "amd-dptc-0", original)
    profile_path = _mk_profile(root)
    backend = AmdDptcBackend(LIMITS, root=root)

    assert backend.get_limits() == TdpLimits(7, 15, 25, 30)
    assert backend.level_limits() == {
        "pl1": {"min": 7, "max": 30},
        "pl2": {"min": 7, "max": 36},
        "pl3": {"min": 7, "max": 42},
    }

    result = backend.set_levels(10, 12, 14, ac=True)

    assert result.ok is True
    assert _read(profile_path) == "custom"
    assert backend.release() is True
    assert _read(profile_path) == "balanced"
    assert {
        rail: int(_read(_fw_path(root, "amd-dptc-0", rail)))
        for rail in RAILS
    } == original


def test_amd_dptc_recovers_owned_profile_and_rails_after_restart(tmp_path):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_firmware(root, "amd-dptc", original)
    profile_path = _mk_profile(root)
    transaction = os.path.join(root, "run/pdc/dptc-transaction.lock")
    ownership = os.path.join(root, "run/pdc/dptc-ownership.lock")
    first = AmdDptcBackend(
        LIMITS,
        root=root,
        safety_lock_path=transaction,
        ownership_lock_path=ownership,
    )

    assert first.set_levels(10, 12, 14, ac=True).ok is True

    restarted = AmdDptcBackend(
        LIMITS,
        root=root,
        safety_lock_path=transaction,
        ownership_lock_path=ownership,
    )
    assert restarted.safety_locked is True
    assert restarted.recover_runtime_transaction()["ok"] is True
    assert _read(profile_path) == "balanced"
    assert {
        rail: int(_read(_fw_path(root, "amd-dptc", rail)))
        for rail in RAILS
    } == original


def test_amd_dptc_rolls_back_profile_and_rails_on_readback_mismatch(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_firmware(root, "amd-dptc", original)
    profile_path = _mk_profile(root)
    backend = AmdDptcBackend(LIMITS, root=root)
    real_read = backend._read_int
    pl1_reads = 0

    def lie_once(path):
        nonlocal pl1_reads
        if path == _fw_path(root, "amd-dptc", "pl1"):
            pl1_reads += 1
            if pl1_reads == 2:
                return 9
        return real_read(path)

    monkeypatch.setattr(backend, "_read_int", lie_once)

    result = backend.set_levels(10, 12, 14, ac=True)

    assert result.ok is False
    assert "rollback confirmed" in result.detail
    assert _read(profile_path) == "balanced"
    assert {
        rail: int(_read(_fw_path(root, "amd-dptc", rail)))
        for rail in RAILS
    } == original


def test_amd_dptc_attempts_all_restores_when_one_rollback_write_fails(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_firmware(root, "amd-dptc", original)
    profile_path = _mk_profile(root)
    backend = AmdDptcBackend(LIMITS, root=root)
    real_read = backend._read_int
    real_write = backend._write
    pl1_reads = 0

    def mismatch_after_write(path):
        nonlocal pl1_reads
        if path == _fw_path(root, "amd-dptc", "pl1"):
            pl1_reads += 1
            if pl1_reads == 2:
                return 9
        return real_read(path)

    def fail_pl2_restore(path, value):
        if path == _fw_path(root, "amd-dptc", "pl2") and value == original["pl2"]:
            return False
        return real_write(path, value)

    monkeypatch.setattr(backend, "_read_int", mismatch_after_write)
    monkeypatch.setattr(backend, "_write", fail_pl2_restore)

    result = backend.set_levels(10, 12, 14, ac=True)

    assert result.ok is False
    assert "rollback failed" in result.detail
    assert _read(_fw_path(root, "amd-dptc", "pl1")) == "15"
    assert _read(_fw_path(root, "amd-dptc", "pl3")) == "25"
    assert _read(profile_path) == "balanced"
    writes = []
    monkeypatch.setattr(
        backend,
        "_write",
        lambda path, value: writes.append((path, value)) or real_write(path, value),
    )

    blocked = backend.set_levels(11, 13, 15, ac=True)

    assert blocked.ok is False
    assert blocked.detail.startswith("firmware write circuit open:")
    assert writes == []
    monkeypatch.setattr(backend, "_write", real_write)
    assert backend.release() is True
    assert {
        rail: int(_read(_fw_path(root, "amd-dptc", rail)))
        for rail in RAILS
    } == original
    assert _read(profile_path) == "balanced"


def test_msi_a8_requires_exact_board_and_complete_native_abi(tmp_path):
    root = str(tmp_path)
    _mk_firmware(root, "msi-wmi-platform")
    _mk_dmi(root, "MS-1T42")
    nearby = MsiClawA8FirmwareBackend(LIMITS, root=root)
    assert nearby.supported is False

    _mk_dmi(root, "MS-1T8K")
    os.remove(_fw_path(root, "msi-wmi-platform", "pl3"))
    partial = MsiClawA8FirmwareBackend(LIMITS, root=root)
    assert partial.supported is False

    _write(_fw_path(root, "msi-wmi-platform", "pl3"), 25)
    exact = MsiClawA8FirmwareBackend(LIMITS, root=root)
    assert exact.supported is True
    assert exact.name == "msi-claw-a8-firmware"


def test_msi_a8_transaction_releases_snapshot(tmp_path):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_firmware(root, "msi-wmi-platform", original)
    _mk_dmi(root, "MS-1T8K")
    backend = MsiClawA8FirmwareBackend(LIMITS, root=root)

    assert backend.set_levels(10, 12, 14, ac=True).ok is True
    assert backend.release() is True
    assert {
        rail: int(_read(_fw_path(root, "msi-wmi-platform", rail)))
        for rail in RAILS
    } == original


def test_msi_a8_recovers_owned_rails_after_restart(tmp_path):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_firmware(root, "msi-wmi-platform", original)
    _mk_dmi(root, "MS-1T8K")
    transaction = os.path.join(root, "run/pdc/msi-a8-transaction.lock")
    ownership = os.path.join(root, "run/pdc/msi-a8-ownership.lock")
    first = MsiClawA8FirmwareBackend(
        LIMITS,
        root=root,
        safety_lock_path=transaction,
        ownership_lock_path=ownership,
    )

    assert first.set_levels(10, 12, 14, ac=True).ok is True

    restarted = MsiClawA8FirmwareBackend(
        LIMITS,
        root=root,
        safety_lock_path=transaction,
        ownership_lock_path=ownership,
    )
    assert restarted.safety_locked is True
    assert restarted.recover_runtime_transaction()["ok"] is True
    assert {
        rail: int(_read(_fw_path(root, "msi-wmi-platform", rail)))
        for rail in RAILS
    } == original


def test_msi_a8_uses_native_per_rail_ceilings(tmp_path):
    root = str(tmp_path)
    _mk_firmware(root, "msi-wmi-platform")
    _mk_dmi(root, "MS-1T8K")
    backend = MsiClawA8FirmwareBackend(
        TdpLimits(min_w=6, default_w=17, max_w=35, max_ac_w=35),
        root=root,
    )

    assert backend.level_limits() == {
        "pl1": {"min": 6, "max": 35},
        "pl2": {"min": 6, "max": 37},
        "pl3": {"min": 6, "max": 55},
    }


def test_msi_a8_rolls_back_after_partial_failure(tmp_path, monkeypatch):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_firmware(root, "msi-wmi-platform", original)
    _mk_dmi(root, "MS-1T8K")
    backend = MsiClawA8FirmwareBackend(LIMITS, root=root)
    real_write = backend._write
    failed = False

    def fail_once(path, value):
        nonlocal failed
        if path == _fw_path(root, "msi-wmi-platform", "pl2") and not failed:
            failed = True
            return False
        return real_write(path, value)

    monkeypatch.setattr(backend, "_write", fail_once)

    result = backend.set_levels(10, 12, 14, ac=True)

    assert result.ok is False
    assert "rollback confirmed" in result.detail
    assert {
        rail: int(_read(_fw_path(root, "msi-wmi-platform", rail)))
        for rail in RAILS
    } == original


def test_msi_a8_attempts_all_restores_when_one_rollback_write_fails(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    original = {"pl1": 15, "pl2": 20, "pl3": 25}
    _mk_firmware(root, "msi-wmi-platform", original)
    _mk_dmi(root, "MS-1T8K")
    backend = MsiClawA8FirmwareBackend(LIMITS, root=root)
    real_read = backend._read_int
    real_write = backend._write
    pl1_reads = 0

    def mismatch_after_write(path):
        nonlocal pl1_reads
        if path == _fw_path(root, "msi-wmi-platform", "pl1"):
            pl1_reads += 1
            if pl1_reads == 2:
                return 9
        return real_read(path)

    def fail_pl2_restore(path, value):
        if path == _fw_path(root, "msi-wmi-platform", "pl2") and value == original["pl2"]:
            return False
        return real_write(path, value)

    monkeypatch.setattr(backend, "_read_int", mismatch_after_write)
    monkeypatch.setattr(backend, "_write", fail_pl2_restore)

    result = backend.set_levels(10, 12, 14, ac=True)

    assert result.ok is False
    assert "rollback failed" in result.detail
    assert _read(_fw_path(root, "msi-wmi-platform", "pl1")) == "15"
    assert _read(_fw_path(root, "msi-wmi-platform", "pl3")) == "25"
    writes = []
    monkeypatch.setattr(
        backend,
        "_write",
        lambda path, value: writes.append((path, value)) or real_write(path, value),
    )

    blocked = backend.set_levels(11, 13, 15, ac=True)

    assert blocked.ok is False
    assert blocked.detail.startswith("firmware write circuit open:")
    assert writes == []
    monkeypatch.setattr(backend, "_write", real_write)
    assert backend.release() is True
    assert {
        rail: int(_read(_fw_path(root, "msi-wmi-platform", rail)))
        for rail in RAILS
    } == original
