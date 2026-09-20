import os

from device_profiles import DEVICE_TABLE
from tdp.factory import select_backend
from tdp.firmware_attr import FirmwareAttrBackend


_MMIO = "intel-rapl-mmio/intel-rapl-mmio:0"
_MSR = "intel-rapl/intel-rapl:0"


def _claw_profile():
    return next(
        profile
        for profile in DEVICE_TABLE
        if profile.key == "msi_claw_8_ai_plus"
    )


def _write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(str(value))


def _make_claw_dmi(root):
    base = os.path.join(root, "sys/class/dmi/id")
    _write(
        os.path.join(base, "sys_vendor"),
        "Micro-Star International Co., Ltd.",
    )
    _write(os.path.join(base, "product_name"), "Claw 8 AI+ A2VM")


def _make_firmware(root, pl1=17, pl2=17):
    base = os.path.join(
        root,
        "sys/class/firmware-attributes/msi-wmi-platform/attributes",
    )
    for attr, value, maximum in (
        ("ppt_pl1_spl", pl1, 30),
        ("ppt_pl2_sppt", pl2, 37),
    ):
        directory = os.path.join(base, attr)
        _write(os.path.join(directory, "current_value"), value)
        _write(os.path.join(directory, "min_value"), 8)
        _write(os.path.join(directory, "max_value"), maximum)
    return base


def _make_rapl(root, base, pl1, pl2):
    directory = os.path.join(root, "sys/devices/virtual/powercap", base)
    _write(os.path.join(directory, "name"), "package-0")
    _write(os.path.join(directory, "constraint_0_name"), "long_term")
    _write(
        os.path.join(directory, "constraint_0_power_limit_uw"),
        pl1 * 1_000_000,
    )
    _write(os.path.join(directory, "constraint_1_name"), "short_term")
    _write(
        os.path.join(directory, "constraint_1_power_limit_uw"),
        pl2 * 1_000_000,
    )
    return directory


def _read(path):
    with open(path) as handle:
        return int(handle.read().strip())


def _select(root):
    return select_backend(
        _claw_profile(),
        root=root,
        ryzenadj_resolve=lambda: None,
    )


def test_auto_tdp_owns_firmware_and_both_rapl_surfaces(tmp_path):
    root = str(tmp_path)
    _make_claw_dmi(root)
    firmware = _make_firmware(root)
    mmio = _make_rapl(root, _MMIO, 22, 37)
    msr = _make_rapl(root, _MSR, 30, 37)

    backend = _select(root)

    assert backend.name == "firmware-attr:msi-wmi-platform"
    assert backend.auto_tdp_safe is True
    result = backend.apply_auto_targets({"pl1": 13, "pl2": 13}, ac=False)
    assert result.ok is True
    assert _read(os.path.join(firmware, "ppt_pl1_spl/current_value")) == 13
    assert _read(os.path.join(firmware, "ppt_pl2_sppt/current_value")) == 13
    assert _read(os.path.join(mmio, "constraint_0_power_limit_uw")) == 13_000_000
    assert _read(os.path.join(mmio, "constraint_1_power_limit_uw")) == 13_000_000
    assert _read(os.path.join(msr, "constraint_0_power_limit_uw")) == 13_000_000
    assert _read(os.path.join(msr, "constraint_1_power_limit_uw")) == 13_000_000

    assert backend.release() is True
    assert _read(os.path.join(firmware, "ppt_pl1_spl/current_value")) == 17
    assert _read(os.path.join(firmware, "ppt_pl2_sppt/current_value")) == 17
    assert _read(os.path.join(mmio, "constraint_0_power_limit_uw")) == 22_000_000
    assert _read(os.path.join(mmio, "constraint_1_power_limit_uw")) == 37_000_000
    assert _read(os.path.join(msr, "constraint_0_power_limit_uw")) == 30_000_000
    assert _read(os.path.join(msr, "constraint_1_power_limit_uw")) == 37_000_000


def test_manual_tdp_does_not_touch_rapl(tmp_path):
    root = str(tmp_path)
    _make_claw_dmi(root)
    firmware = _make_firmware(root)
    mmio = _make_rapl(root, _MMIO, 22, 37)
    msr = _make_rapl(root, _MSR, 30, 37)
    backend = _select(root)

    result = backend.set_levels(19, 23, 23, ac=False)

    assert result.ok is True
    assert _read(os.path.join(firmware, "ppt_pl1_spl/current_value")) == 19
    assert _read(os.path.join(firmware, "ppt_pl2_sppt/current_value")) == 23
    assert _read(os.path.join(mmio, "constraint_0_power_limit_uw")) == 22_000_000
    assert _read(os.path.join(mmio, "constraint_1_power_limit_uw")) == 37_000_000
    assert _read(os.path.join(msr, "constraint_0_power_limit_uw")) == 30_000_000
    assert _read(os.path.join(msr, "constraint_1_power_limit_uw")) == 37_000_000


def test_two_rail_firmware_without_complete_rapl_stays_auto_unsafe(tmp_path):
    root = str(tmp_path)
    _make_claw_dmi(root)
    _make_firmware(root)
    _make_rapl(root, _MMIO, 22, 37)

    backend = _select(root)

    assert backend.name == "firmware-attr:msi-wmi-platform"
    assert backend.auto_tdp_safe is False


def test_non_a2vm_firmware_keeps_strict_three_rail_rule(tmp_path):
    root = str(tmp_path)
    base = os.path.join(root, "sys/class/dmi/id")
    _write(
        os.path.join(base, "sys_vendor"),
        "Micro-Star International Co., Ltd.",
    )
    _write(os.path.join(base, "product_name"), "Claw 8 AI+")
    _make_firmware(root)
    _make_rapl(root, _MMIO, 22, 37)
    _make_rapl(root, _MSR, 30, 37)

    backend = _select(root)

    assert backend.auto_tdp_safe is False


def test_partial_rapl_failure_restores_every_surface(tmp_path, monkeypatch):
    root = str(tmp_path)
    _make_claw_dmi(root)
    firmware = _make_firmware(root)
    mmio = _make_rapl(root, _MMIO, 22, 37)
    msr = _make_rapl(root, _MSR, 30, 37)
    backend = _select(root)
    real_write = backend._auto_rapl._write
    failed = False

    def fail_msr_pl2_once(path, value):
        nonlocal failed
        target = os.path.join(msr, "constraint_1_power_limit_uw")
        if path == target and value == 13_000_000 and not failed:
            failed = True
            return False
        return real_write(path, value)

    monkeypatch.setattr(backend._auto_rapl, "_write", fail_msr_pl2_once)

    result = backend.apply_auto_targets({"pl1": 13, "pl2": 13}, ac=False)

    assert result.ok is False
    assert _read(os.path.join(firmware, "ppt_pl1_spl/current_value")) == 17
    assert _read(os.path.join(firmware, "ppt_pl2_sppt/current_value")) == 17
    assert _read(os.path.join(mmio, "constraint_0_power_limit_uw")) == 22_000_000
    assert _read(os.path.join(mmio, "constraint_1_power_limit_uw")) == 37_000_000
    assert _read(os.path.join(msr, "constraint_0_power_limit_uw")) == 30_000_000
    assert _read(os.path.join(msr, "constraint_1_power_limit_uw")) == 37_000_000


def test_manual_transaction_recovery_uses_the_manual_firmware_instance(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    _make_claw_dmi(root)
    firmware = _make_firmware(root)
    _make_rapl(root, _MMIO, 22, 37)
    _make_rapl(root, _MSR, 30, 37)
    backend = _select(root)
    real_clear = backend._manual._safety_lock.clear
    clear_calls = 0

    def fail_first_clear():
        nonlocal clear_calls
        clear_calls += 1
        return False if clear_calls == 1 else real_clear()

    monkeypatch.setattr(backend._manual._safety_lock, "clear", fail_first_clear)

    result = backend.set_levels(19, 23, 23, ac=False)

    assert result.ok is False
    assert backend.safety_locked is True
    assert backend.recover_runtime_transaction()["ok"] is True
    assert backend.safety_locked is False
    assert _read(os.path.join(firmware, "ppt_pl1_spl/current_value")) == 17
    assert _read(os.path.join(firmware, "ppt_pl2_sppt/current_value")) == 17


def test_present_but_unreadable_firmware_never_falls_through_to_rapl_auto(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    _make_claw_dmi(root)
    _make_firmware(root)
    _make_rapl(root, _MMIO, 22, 37)
    _make_rapl(root, _MSR, 30, 37)
    real_read = FirmwareAttrBackend._read_int

    def fail_firmware_pl1(self, path):
        if "msi-wmi-platform" in path and path.endswith(
            "ppt_pl1_spl/current_value"
        ):
            return None
        return real_read(self, path)

    monkeypatch.setattr(FirmwareAttrBackend, "_read_int", fail_firmware_pl1)

    backend = _select(root)

    assert backend.name == "firmware-attr:msi-wmi-platform"
    assert backend.auto_tdp_safe is False
    assert backend.selection_ready() is False
    assert all(item["candidate"] != "intel" for item in backend.probe_trace)


def test_manual_transaction_recovers_after_backend_restart(tmp_path, monkeypatch):
    root = str(tmp_path)
    _make_claw_dmi(root)
    firmware = _make_firmware(root)
    _make_rapl(root, _MMIO, 22, 37)
    _make_rapl(root, _MSR, 30, 37)
    interrupted = _select(root)
    monkeypatch.setattr(interrupted._manual._safety_lock, "clear", lambda: False)

    result = interrupted.set_levels(19, 23, 23, ac=False)
    restarted = _select(root)

    assert result.ok is False
    assert restarted.safety_locked is True
    assert restarted.recover_runtime_transaction()["ok"] is True
    assert restarted.safety_locked is False
    assert _read(os.path.join(firmware, "ppt_pl1_spl/current_value")) == 17
    assert _read(os.path.join(firmware, "ppt_pl2_sppt/current_value")) == 17
