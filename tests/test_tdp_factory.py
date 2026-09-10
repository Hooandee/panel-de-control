import dataclasses
import json
import os

import pytest

from device_profiles import DEVICE_TABLE, GENERIC
from tdp import factory
from tdp.backend import NullBackend
from tdp.factory import select_backend
from tdp.reconcile import build_targets
from tdp.types import RailReading, TdpObservation


def _p(key):
    return next(x for x in DEVICE_TABLE if x.key == key)


def _mk_fw(root, driver, pl1_max=35):
    base = os.path.join(root, "sys/class/firmware-attributes", driver, "attributes")
    for attr, mx in (("ppt_pl1_spl", pl1_max), ("ppt_pl2_sppt", 45), ("ppt_pl3_fppt", 55)):
        d = os.path.join(base, attr)
        os.makedirs(d, exist_ok=True)
        for f, v in (("current_value", 15), ("min_value", 5), ("max_value", mx)):
            with open(os.path.join(d, f), "w") as fh:
                fh.write(str(v))


def _mk_hwmon(root):
    d = os.path.join(root, "sys/class/hwmon/hwmon0")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "name"), "w") as f:
        f.write("amdgpu")
    with open(os.path.join(d, "power1_cap"), "w") as f:
        f.write("15000000")
    with open(os.path.join(d, "power1_label"), "w") as f:
        f.write("slowPPT")
    with open(os.path.join(d, "power2_cap"), "w") as f:
        f.write("15000000")
    with open(os.path.join(d, "power2_label"), "w") as f:
        f.write("fastPPT")


def _mk_dmi(root, vendor, product):
    base = os.path.join(root, "sys/class/dmi/id")
    os.makedirs(base, exist_ok=True)
    for name, value in (("sys_vendor", vendor), ("product_name", product)):
        with open(os.path.join(base, name), "w") as f:
            f.write(value)


def _mk_platform_profile(root, current="balanced"):
    base = os.path.join(root, "sys/class/platform-profile/platform-profile-0")
    os.makedirs(base, exist_ok=True)
    for name, value in (
        ("name", "lenovo-wmi-gamezone"),
        ("profile", current),
        ("choices", "low-power balanced performance custom"),
    ):
        with open(os.path.join(base, name), "w") as handle:
            handle.write(value)


def _mk_readable_ryzenadj(root):
    path = os.path.join(root, "fake-ryzenadj")
    with open(path, "w") as handle:
        handle.write(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"-i\" ]; then\n"
            "  printf '| STAPM LIMIT | 15.000 | stapm-limit |\\n'\n"
            "fi\n"
        )
    os.chmod(path, 0o755)
    return path


def _mk_asus_legacy(root):
    base = os.path.join(root, "sys/devices/platform/asus-nb-wmi")
    os.makedirs(base, exist_ok=True)
    for name in ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_fppt"):
        with open(os.path.join(base, name), "w") as handle:
            handle.write("15")


def _set_fw_max(root, rail, value):
    path = os.path.join(
        root,
        "sys/class/firmware-attributes/lenovo-wmi-other-0/attributes",
        rail,
        "max_value",
    )
    with open(path, "w") as handle:
        handle.write(str(value))


def _set_fw_current(root, rail, value):
    path = os.path.join(
        root,
        "sys/class/firmware-attributes/lenovo-wmi-other-0/attributes",
        rail,
        "current_value",
    )
    with open(path, "w") as handle:
        handle.write(str(value))


def _mk_legion_firmware(root, product_name, profile, current=(21, 17, 36)):
    _mk_fw(root, "lenovo-wmi-other-0")
    _mk_dmi(root, "LENOVO", product_name)
    _mk_platform_profile(root, current=profile)
    for attr, value in zip(
        ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"),
        current,
    ):
        _set_fw_current(root, attr, value)


def _arm_lenovo_transaction_lock(root, profile, snapshot=None):
    lock_path = os.path.join(
        root,
        "run/panel-de-control/firmware-lenovo-wmi-other.lock",
    )
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "w") as handle:
        json.dump(
            {
                "state": "rollback_failed",
                "detail": "firmware transaction recovery failed",
                "snapshot": snapshot or {
                    "firmware-attr:lenovo-wmi-other/pl1": 25,
                    "firmware-attr:lenovo-wmi-other/pl2": 25,
                    "firmware-attr:lenovo-wmi-other/pl3": 25,
                },
                "profile": profile,
            },
            handle,
        )
    return lock_path


def _locked_legion_backend(
    root,
    product_name="83L3",
    current_profile="low-power",
    saved_profile=None,
    snapshot=None,
):
    _mk_legion_firmware(root, product_name, current_profile)
    lock_path = _arm_lenovo_transaction_lock(
        root,
        saved_profile or current_profile,
        snapshot=snapshot,
    )
    backend = select_backend(
        _p("legion_go_s"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )
    return backend, lock_path


def _observation(backend, pl1, pl2, pl3):
    return TdpObservation(
        readable=True,
        surfaces={
            backend.name: {
                "pl1": RailReading(pl1),
                "pl2": RailReading(pl2),
                "pl3": RailReading(pl3),
            },
        },
    )


_NO_RYZENADJ = lambda: None  # noqa: E731


def test_rog_uses_asus_armoury_firmware_attr(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "asus-armoury")
    b = select_backend(_p("rog_xbox_ally_x"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and "asus-armoury" in b.name
    assert b.probe_trace == ({
        "candidate": "asus",
        "backend": "firmware-attr:asus-armoury",
        "supported": True,
    },)
    assert b.diagnostics()["readback_settle_ms"] == 0


def test_flow_uses_asus_armoury_and_publishes_live_narrowed_limits(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "asus-armoury", pl1_max=42)
    backend = select_backend(
        _p("rog_flow_z13"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    assert backend.name == "firmware-attr:asus-armoury"
    assert backend.get_limits().max_w == 42
    assert backend.get_limits().max_ac_w == 42


def test_flow_keeps_recoverable_firmware_backend_but_reports_invalid_bounds_unready(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "asus-armoury", pl1_max=0)

    backend = select_backend(
        _p("rog_flow_z13"),
        root=root,
        ryzenadj_resolve=lambda: "/bin/true",
    )

    assert backend.name == "firmware-attr:asus-armoury"
    assert backend.supported is True
    assert backend.ready() is False


@pytest.mark.parametrize(
    "os_release",
    (
        'ID=bazzite\nPRETTY_NAME="Bazzite 43"\n',
        'ID=bazzite\nPRETTY_NAME="Bazzite 44"\n',
        'ID=steamos\nPRETTY_NAME="SteamOS Holo"\n',
        'ID=cachyos\nPRETTY_NAME="CachyOS"\n',
    ),
)
def test_tdp_backend_selection_is_independent_of_linux_distribution(
    tmp_path,
    os_release,
):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "etc"), exist_ok=True)
    with open(os.path.join(root, "etc/os-release"), "w") as handle:
        handle.write(os_release)
    _mk_fw(root, "asus-armoury", pl1_max=42)

    backend = select_backend(
        _p("rog_flow_z13"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    assert backend.name == "firmware-attr:asus-armoury"
    assert backend.get_limits().max_w == 42


def test_only_exact_dual_interface_xbox_ally_x_gets_authoritative_reassert(tmp_path):
    exact_root = str(tmp_path / "exact")
    _mk_fw(exact_root, "asus-armoury")
    _mk_asus_legacy(exact_root)
    _mk_dmi(
        exact_root,
        "ASUSTeK COMPUTER INC.",
        "ROG Xbox Ally X RC73XA_RC73XA",
    )
    exact = select_backend(
        _p("rog_xbox_ally_x"),
        root=exact_root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    missing_legacy_root = str(tmp_path / "missing-legacy")
    _mk_fw(missing_legacy_root, "asus-armoury")
    _mk_dmi(
        missing_legacy_root,
        "ASUSTeK COMPUTER INC.",
        "ROG Xbox Ally X RC73XA_RC73XA",
    )
    missing_legacy = select_backend(
        _p("rog_xbox_ally_x"),
        root=missing_legacy_root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    partial_primary_root = str(tmp_path / "partial-primary")
    _mk_fw(partial_primary_root, "asus-armoury")
    _mk_asus_legacy(partial_primary_root)
    _mk_dmi(
        partial_primary_root,
        "ASUSTeK COMPUTER INC.",
        "ROG Xbox Ally X RC73XA_RC73XA",
    )
    partial_pl3 = os.path.join(
        partial_primary_root,
        "sys/class/firmware-attributes/asus-armoury/attributes/ppt_pl3_fppt",
    )
    for name in ("current_value", "min_value", "max_value"):
        os.remove(os.path.join(partial_pl3, name))
    os.rmdir(partial_pl3)
    partial_primary = select_backend(
        _p("rog_xbox_ally_x"),
        root=partial_primary_root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    other_root = str(tmp_path / "other")
    _mk_fw(other_root, "asus-armoury")
    _mk_asus_legacy(other_root)
    _mk_dmi(other_root, "ASUSTeK COMPUTER INC.", "ROG Ally X RC72LA")
    other = select_backend(
        _p("rog_ally_x"),
        root=other_root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    assert exact.authoritative_reassert_s == 15.0
    assert missing_legacy.authoritative_reassert_s is None
    assert partial_primary.authoritative_reassert_s is None
    assert other.authoritative_reassert_s is None


def test_legion_uses_lenovo_firmware_attr(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0")
    b = select_backend(_p("legion_go_2"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and "lenovo-wmi-other" in b.name
    assert b.diagnostics()["readback_settle_ms"] == 0


def test_new_experimental_profile_defers_ryzenadj_probe_and_rejects_before_write(tmp_path):
    backend = select_backend(
        _p("onexplayer_f1"),
        root=str(tmp_path),
        ryzenadj_resolve=lambda: "/bin/true",
    )

    assert backend.supported is True
    assert backend.name == "ryzenadj"
    assert [item["candidate"] for item in backend.probe_trace] == [
        "asus",
        "lenovo",
        "msi",
        "ryzenadj",
    ]
    result = backend.set_tdp(20, ac=True)
    assert result.ok is False
    assert "readback unavailable before write" in result.detail


def test_gpd_win_mini_backend_reserves_55w_for_explicit_ac_unlock(tmp_path):
    backend = select_backend(
        _p("gpd_win_mini_2025"),
        root=str(tmp_path),
        ryzenadj_resolve=lambda: "/bin/true",
    )

    assert backend.get_limits().max_ac_w == 35
    assert backend._write_limits.max_w == 35
    assert backend._write_limits.max_ac_w == 55


def test_factory_keeps_runtime_locked_gpd_backend_available_for_safe_recovery(tmp_path):
    lock = tmp_path / "run/panel-de-control/ryzenadj-gpd_win_mini_2025.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("circuit_open_restored", encoding="utf-8")

    backend = select_backend(
        _p("gpd_win_mini_2025"),
        root=str(tmp_path),
        ryzenadj_resolve=lambda: "/bin/true",
    )

    assert backend.name == "ryzenadj"
    assert backend.supported is False
    assert backend.safety_locked is True
    assert backend.recover_safe_range() is True


def test_only_exact_legion_go_s_83n6_gets_measured_rail_floors(tmp_path):
    exact_root = str(tmp_path / "exact")
    _mk_fw(exact_root, "lenovo-wmi-other-0")
    _mk_dmi(exact_root, "LENOVO", "83N6")
    exact = select_backend(
        _p("legion_go_s"),
        root=exact_root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    nearby_root = str(tmp_path / "nearby")
    _mk_fw(nearby_root, "lenovo-wmi-other-0")
    _mk_dmi(nearby_root, "LENOVO", "83L3")
    nearby = select_backend(
        _p("legion_go_s"),
        root=nearby_root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    assert getattr(exact, "_rail_floors", None) == {"pl2": 15, "pl3": 20}
    assert getattr(nearby, "_rail_floors", None) == {}


@pytest.mark.parametrize("profile", ("low-power", "balanced", "performance"))
def test_exact_legion_go_s_83l3_recovers_named_profile_without_restoring_rails(
    tmp_path,
    monkeypatch,
    profile,
):
    root = str(tmp_path)
    backend, lock_path = _locked_legion_backend(root, current_profile=profile)
    original_write = backend._write

    def firmware_owns_rails(path, value):
        if path.endswith("current_value"):
            return False
        return original_write(path, value)

    monkeypatch.setattr(backend, "_write", firmware_owns_rails)

    recovered = backend.recover_runtime_transaction()

    assert recovered["ok"] is True
    assert backend.read_profile() == profile
    assert backend.read_applied() == 21
    assert not os.path.exists(lock_path)


def test_exact_legion_go_s_83l3_confirms_named_profile_rollback_with_live_rails(
    tmp_path,
    monkeypatch,
):
    root = str(tmp_path)
    _mk_legion_firmware(root, "83L3", "low-power", current=(25, 25, 25))
    backend = select_backend(
        _p("legion_go_s"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )
    profile_path = os.path.join(
        root,
        "sys/class/platform-profile/platform-profile-0/profile",
    )
    original_write = backend._write

    def recalculate_named_profile_rails(path, value):
        if path.endswith("ppt_pl3_fppt/current_value") and value == 15:
            return original_write(path, 20)
        written = original_write(path, value)
        if path == profile_path and value == "low-power":
            _set_fw_current(root, "ppt_pl1_spl", 21)
            _set_fw_current(root, "ppt_pl2_sppt", 17)
            _set_fw_current(root, "ppt_pl3_fppt", 36)
        return written

    monkeypatch.setattr(backend, "_write", recalculate_named_profile_rails)

    result = backend.set_levels(15, 15, 15, ac=False)

    assert result.ok is False
    assert result.applied_w == 21
    assert "rollback confirmed" in result.detail
    assert backend.read_profile() == "low-power"
    assert backend.safety_locked is False
    assert backend.ready() is True


@pytest.mark.parametrize(
    ("product_name", "profile"),
    (("83L3", "custom"), ("83N6", "low-power")),
)
def test_legion_go_s_keeps_strict_recovery_outside_83l3_named_profiles(
    tmp_path,
    monkeypatch,
    product_name,
    profile,
):
    root = str(tmp_path)
    backend, lock_path = _locked_legion_backend(
        root,
        product_name=product_name,
        current_profile=profile,
    )
    original_write = backend._write

    def reject_rail_restore(path, value):
        if path.endswith("current_value"):
            return False
        return original_write(path, value)

    monkeypatch.setattr(backend, "_write", reject_rail_restore)

    recovered = backend.recover_runtime_transaction()

    assert recovered["ok"] is False
    assert backend.safety_locked is True
    assert os.path.exists(lock_path)


def test_exact_legion_go_s_83l3_without_platform_profile_recovers_strictly(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0")
    _mk_dmi(root, "LENOVO", "83L3")
    for attr, value in zip(
        ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"),
        (21, 17, 36),
    ):
        _set_fw_current(root, attr, value)
    lock_path = _arm_lenovo_transaction_lock(root, None)
    backend = select_backend(
        _p("legion_go_s"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    recovered = backend.recover_runtime_transaction()

    assert recovered["ok"] is True
    assert backend.read_applied() == 25
    assert not os.path.exists(lock_path)


@pytest.mark.parametrize(
    ("failure", "expected_detail"),
    (
        ("profile-unreadable", "platform-profile=unavailable"),
        ("lock-clear", "runtime lock clear failed"),
        ("unknown-profile", "firmware transaction profile invalid"),
        ("surface-changed", "firmware transaction surfaces changed"),
        ("rail-unreadable", "pl2=unavailable"),
    ),
)
def test_exact_legion_go_s_83l3_named_recovery_fails_closed(
    tmp_path,
    monkeypatch,
    failure,
    expected_detail,
):
    root = str(tmp_path)
    backend, lock_path = _locked_legion_backend(
        root,
        saved_profile="turbo" if failure == "unknown-profile" else None,
        snapshot=(
            {"firmware-attr:lenovo-wmi-other/pl1": 25}
            if failure == "surface-changed"
            else None
        ),
    )
    if failure == "profile-unreadable":
        monkeypatch.setattr(backend, "read_profile", lambda: None)
        monkeypatch.setattr("tdp.firmware_attr.time.sleep", lambda _delay: None)
    elif failure == "lock-clear":
        monkeypatch.setattr(backend._safety_lock, "clear", lambda: False)
    elif failure == "rail-unreadable":
        _set_fw_current(root, "ppt_pl2_sppt", "invalid")

    recovered = backend.recover_runtime_transaction()

    assert recovered["ok"] is False
    assert expected_detail in recovered["detail"]
    assert backend.safety_locked is True
    assert os.path.exists(lock_path)


@pytest.mark.parametrize("product_name", ("83L3", "83N6"))
def test_exact_legion_go_s_waits_for_async_firmware_readback(
    tmp_path,
    monkeypatch,
    product_name,
):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0")
    _mk_dmi(root, "LENOVO", product_name)
    backend = select_backend(
        _p("legion_go_s"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )
    stale = _observation(backend, 15, 15, 15)
    original_observe = backend.observe
    observations = iter((stale, stale, stale))

    def observe_after_firmware_settles():
        return next(observations, None) or original_observe()

    sleeps = []
    monkeypatch.setattr(backend, "observe", observe_after_firmware_settles)
    monkeypatch.setattr("tdp.firmware_attr.time.sleep", sleeps.append)

    result = backend.set_levels(20, 20, 20, ac=True)

    assert result.ok is True
    assert result.applied_w == 20
    assert sleeps == [0.05, 0.10, 0.20]
    assert backend.diagnostics()["readback_settle_ms"] == 750


def test_exact_legion_go_s_83n6_applies_profile_safe_target_despite_low_firmware_max(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0", pl1_max=15)
    _mk_dmi(root, "LENOVO", "83N6")
    _set_fw_max(root, "ppt_pl2_sppt", 15)
    _set_fw_max(root, "ppt_pl3_fppt", 20)

    backend = select_backend(
        _p("legion_go_s"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )
    requested = {"pl1": 30, "pl2": 30, "pl3": 30}
    targets = build_targets(requested, backend.level_limits(), backend.observe())
    result = backend.apply_targets(targets.target, ac=True)

    assert targets.target == requested
    assert result.ok is True
    assert result.applied_w == 30


def test_exact_legion_go_s_83n6_does_not_unlock_unverified_boost_range(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0", pl1_max=15)
    _mk_dmi(root, "LENOVO", "83N6")
    _set_fw_max(root, "ppt_pl2_sppt", 15)
    _set_fw_max(root, "ppt_pl3_fppt", 20)
    backend = select_backend(
        _p("legion_go_s"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    targets = build_targets(
        {"pl1": 999, "pl2": 999, "pl3": 999},
        backend.level_limits(),
        backend.observe(),
    )

    assert targets.target == {"pl1": 40, "pl2": 40, "pl3": 40}


def test_exact_legion_go_s_83n6_uses_non_sentinel_live_max(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0", pl1_max=25)
    _mk_dmi(root, "LENOVO", "83N6")
    _set_fw_max(root, "ppt_pl2_sppt", 30)
    _set_fw_max(root, "ppt_pl3_fppt", 35)
    backend = select_backend(
        _p("legion_go_s"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    rails = backend.observe().surfaces[backend.name]

    assert {rail: reading.max_w for rail, reading in rails.items()} == {
        "pl1": 25,
        "pl2": 30,
        "pl3": 35,
    }


def test_exact_legion_go_s_83n6_diagnostics_keep_reported_sentinel_max(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0", pl1_max=15)
    _mk_dmi(root, "LENOVO", "83N6")
    _set_fw_max(root, "ppt_pl2_sppt", 15)
    _set_fw_max(root, "ppt_pl3_fppt", 20)
    backend = select_backend(
        _p("legion_go_s"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    assert backend.diagnostics() == {
        "boost_capped_to_active": True,
        "ignored_live_maxes": {"pl1": 15, "pl2": 15, "pl3": 20},
        "readback_settle_ms": 750,
        "reported_live_bounds": {
            "pl1": {"min": 5, "max": 15},
            "pl2": {"min": 5, "max": 15},
            "pl3": {"min": 5, "max": 20},
        },
    }


def test_nearby_legion_go_s_still_honours_low_firmware_max(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0", pl1_max=15)
    _mk_dmi(root, "LENOVO", "83L3")
    _set_fw_max(root, "ppt_pl2_sppt", 15)
    _set_fw_max(root, "ppt_pl3_fppt", 20)
    backend = select_backend(
        _p("legion_go_s"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    targets = build_targets(
        {"pl1": 30, "pl2": 30, "pl3": 30},
        backend.level_limits(),
        backend.observe(),
    )

    assert targets.target == {"pl1": 15, "pl2": 15, "pl3": 20}


def test_exact_legion_go_s_83n6_without_pl1_firmware_attr_uses_ryzenadj(tmp_path):
    root = str(tmp_path)
    base = os.path.join(
        root,
        "sys/class/firmware-attributes/lenovo-wmi-other-0/attributes",
    )
    for attr in ("ppt_cpu_cl", "ppt_pl2_sppt", "ppt_pl3_fppt"):
        path = os.path.join(base, attr)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "current_value"), "w") as handle:
            handle.write("15")
    _mk_dmi(root, "LENOVO", "83N6")

    backend = select_backend(
        _p("legion_go_s"),
        root=root,
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
    )

    assert backend.name == "ryzenadj"
    assert [item["candidate"] for item in backend.probe_trace] == [
        "lenovo",
        "asus",
        "msi",
        "ryzenadj",
    ]


def test_generic_device_does_not_get_83n6_rail_floors_from_dmi_alone(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0")
    _mk_dmi(root, "LENOVO", "83N6")

    backend = select_backend(
        GENERIC,
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    assert getattr(backend, "_rail_floors", None) == {}


def test_msi_uses_msi_firmware_attr(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "msi-wmi-platform")
    b = select_backend(_p("msi_claw_8_ai_plus"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and "msi-wmi-platform" in b.name


def test_msi_claw_a8_never_uses_intel_msi_firmware_attr(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "msi-wmi-platform")

    backend = select_backend(
        _p("msi_claw_a8"),
        root=root,
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
    )

    assert backend.supported is True
    assert backend.name == "ryzenadj"
    assert [item["candidate"] for item in backend.probe_trace] == ["ryzenadj"]


def test_msi_claw_a8_without_ryzenadj_fails_closed(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "msi-wmi-platform")

    backend = select_backend(
        _p("msi_claw_a8"),
        root=root,
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    assert isinstance(backend, NullBackend)
    assert [item["candidate"] for item in backend.probe_trace] == ["ryzenadj"]


def test_steam_deck_uses_hwmon(tmp_path):
    root = str(tmp_path)
    _mk_hwmon(root)
    b = select_backend(_p("steam_deck_oled"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and b.name == "steamdeck-hwmon"


def test_exact_steam_deck_never_falls_through_to_generic_amd_backends(tmp_path):
    backend = select_backend(
        _p("steam_deck_oled"),
        root=str(tmp_path),
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
    )

    assert isinstance(backend, NullBackend)
    assert [item["candidate"] for item in backend.probe_trace] == ["deck"]


def test_steam_machine_does_not_claim_ryzenadj_from_binary_presence(tmp_path):
    # Physical Fremont returns "unsupported model 124" from ryzenadj and exposes no
    # readable CPU watts/limit. A binary on disk is not a supported CPU TDP backend.
    backend = select_backend(
        _p("steam_machine"), root=str(tmp_path),
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert backend.supported is False
    assert backend.name == "unsupported"
    assert "ryzenadj" not in [item["candidate"] for item in backend.probe_trace]


def test_falls_back_to_null_when_nothing_present(tmp_path):
    b = select_backend(_p("rog_ally_x"), root=str(tmp_path), ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported is False and b.name == "unsupported"
    assert [item["candidate"] for item in b.probe_trace] == [
        "asus",
        "asus_nb_wmi",
        "lenovo",
        "msi",
        "ryzenadj",
        "alib",
    ]
    assert all(item["supported"] is False for item in b.probe_trace)


def test_generic_amd_uses_ryzenadj_when_present(tmp_path):
    b = select_backend(GENERIC, root=str(tmp_path), ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.supported and b.name == "ryzenadj"
    assert [item["candidate"] for item in b.probe_trace] == [
        "asus",
        "lenovo",
        "msi",
        "ryzenadj",
    ]


def test_only_exact_gpd_enables_ryzenadj_power_only_retry(tmp_path):
    root = str(tmp_path)
    _mk_dmi(root, "GPD", "G1617-02")
    binary = _mk_readable_ryzenadj(root)

    exact = select_backend(
        _p("gpd_win_mini_2025"),
        root=root,
        ryzenadj_resolve=lambda: binary,
    )
    other = select_backend(
        _p("onexplayer_f1pro"),
        root=root,
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
    )

    assert exact._power_only_retry is True
    assert other._power_only_retry is False


def test_gpd_profile_with_different_dmi_keeps_default_ryzenadj(tmp_path):
    root = str(tmp_path)
    _mk_dmi(root, "GPD", "G1617-02-L")
    binary = _mk_readable_ryzenadj(root)

    backend = select_backend(
        _p("gpd_win_mini_2025"),
        root=root,
        ryzenadj_resolve=lambda: binary,
    )

    assert backend._power_only_retry is False


def test_backend_probe_failure_is_recorded_and_falls_through(tmp_path, monkeypatch):
    calls = []

    def broken():
        calls.append("broken")
        raise OSError("probe failed")

    def working():
        calls.append("working")

        class Working(NullBackend):
            supported = True
            name = "working"

        return Working("x")

    def unreachable():
        calls.append("unreachable")
        raise AssertionError("lazy selection continued after a match")

    monkeypatch.setattr(
        factory,
        "_candidates",
        lambda *args: [broken, working, unreachable],
    )

    backend = select_backend(
        GENERIC,
        root=str(tmp_path),
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    assert backend.name == "working"
    assert calls == ["broken", "working"]
    assert backend.probe_trace == (
        {
            "candidate": "broken",
            "backend": None,
            "supported": False,
            "error": "OSError",
        },
        {
            "candidate": "working",
            "backend": "working",
            "supported": True,
        },
    )


def test_factory_continues_after_a_present_candidate_is_not_ready(
    tmp_path,
    monkeypatch,
):
    calls = []

    def unavailable():
        calls.append("unavailable")

        class Unavailable(NullBackend):
            supported = True
            name = "unavailable"

            def selection_ready(self):
                return False

        return Unavailable("x")

    def working():
        calls.append("working")

        class Working(NullBackend):
            supported = True
            name = "working"

        return Working("x")

    monkeypatch.setattr(
        factory,
        "_candidates",
        lambda *args: [unavailable, working],
    )

    backend = select_backend(
        GENERIC,
        root=str(tmp_path),
        ryzenadj_resolve=_NO_RYZENADJ,
    )

    assert backend.name == "working"
    assert calls == ["unavailable", "working"]
    assert backend.probe_trace[0] == {
        "candidate": "unavailable",
        "backend": "unavailable",
        "supported": True,
        "ready": False,
    }


def _mk_rapl(root):
    d = os.path.join(root, "sys/devices/virtual/powercap/intel-rapl-mmio/intel-rapl-mmio:0")
    os.makedirs(d, exist_ok=True)
    for i, uw in ((0, 30_000_000), (1, 37_000_000)):
        with open(os.path.join(d, f"constraint_{i}_power_limit_uw"), "w") as f:
            f.write(str(uw))


def test_generic_amd_probes_firmware_attr_before_ryzenadj(tmp_path):
    # An unrecognised AMD handheld that exposes a firmware-attributes chip must use
    # it (real rails) instead of falling straight to ryzenadj.
    root = str(tmp_path)
    _mk_fw(root, "asus-armoury")
    b = select_backend(GENERIC, root=root, ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.supported and "asus-armoury" in b.name


def test_generic_amd_uses_lenovo_firmware_attr_when_present(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0")
    b = select_backend(GENERIC, root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and "lenovo-wmi-other" in b.name


def test_generic_intel_uses_rapl_and_not_ryzenadj(tmp_path):
    # An unrecognised Intel handheld must not be captured by ryzenadj (AMD-only)
    # just because the binary exists; RAPL powercap is the correct path.
    root = str(tmp_path)
    _mk_rapl(root)
    intel = dataclasses.replace(GENERIC, vendor="intel")
    b = select_backend(intel, root=root, ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.supported and b.name == "intel-rapl"


def test_generic_intel_never_uses_ryzenadj(tmp_path):
    intel = dataclasses.replace(GENERIC, vendor="intel")
    b = select_backend(intel, root=str(tmp_path), ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.name != "ryzenadj"


def test_known_rog_falls_through_to_ryzenadj(tmp_path):
    # Robustness: if a kernel update drops the ASUS chip, a known AMD device still
    # finds its AMD fallback (ryzenadj) instead of Null. intel-rapl is NOT used on
    # AMD — a RAPL write there can confirm without changing real TDP.
    root = str(tmp_path)
    _mk_rapl(root)
    b = select_backend(_p("rog_ally_x"), root=root, ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.supported and b.name == "ryzenadj"


def test_amd_never_uses_intel_rapl(tmp_path):
    # Even with RAPL present and no ryzenadj, an AMD device must not pick intel-rapl.
    root = str(tmp_path)
    _mk_rapl(root)
    b = select_backend(GENERIC, root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.name != "intel-rapl"


def _mk_acpi_call(root):
    d = os.path.join(root, "proc/acpi")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "call"), "w") as f:
        f.write("not called")


def test_generic_amd_uses_alib_when_acpi_call_present(tmp_path):
    # An unrecognised AMD handheld with no firmware-attributes chip drives TDP
    # via the ALIB acpi_call path (no bundled ryzenadj needed).
    root = str(tmp_path)
    _mk_acpi_call(root)
    b = select_backend(GENERIC, root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and b.name == "acpi-alib"


def test_ryzenadj_precedes_alib(tmp_path):
    # With both generic-AMD backends available, ryzenadj is selected before ALIB.
    root = str(tmp_path)
    _mk_acpi_call(root)
    b = select_backend(GENERIC, root=root, ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.name == "ryzenadj"


def test_onexplayer_apex_prefers_alib_over_ryzenadj(tmp_path):
    root = str(tmp_path)
    _mk_acpi_call(root)

    backend = select_backend(
        _p("onexplayer_apex"),
        root=root,
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
    )

    assert backend.name == "acpi-alib"
    assert [item["candidate"] for item in backend.probe_trace] == ["alib"]


def test_onexplayer_apex_falls_back_to_ryzenadj_without_alib(tmp_path):
    backend = select_backend(
        _p("onexplayer_apex"),
        root=str(tmp_path),
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
    )

    assert backend.name == "ryzenadj"
    assert [item["candidate"] for item in backend.probe_trace] == [
        "alib",
        "ryzenadj",
    ]


def test_firmware_attr_still_wins_over_alib(tmp_path):
    # A firmware-attributes chip must still be chosen ahead of ALIB (real rails).
    root = str(tmp_path)
    _mk_fw(root, "asus-armoury")
    _mk_acpi_call(root)
    b = select_backend(GENERIC, root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert "asus-armoury" in b.name


def test_known_rog_falls_through_to_ryzenadj_before_alib(tmp_path):
    # If a kernel update drops the ASUS chip, a known AMD device reaches its AMD
    # fallback: ryzenadj first, then ALIB. With both available, ryzenadj wins.
    root = str(tmp_path)
    _mk_acpi_call(root)
    b = select_backend(_p("rog_ally_x"), root=root, ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.name == "ryzenadj"


def test_known_rog_falls_through_to_alib_when_no_ryzenadj(tmp_path):
    # ALIB still catches a known AMD device when the ryzenadj binary is absent.
    root = str(tmp_path)
    _mk_acpi_call(root)
    b = select_backend(_p("rog_ally_x"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.name == "acpi-alib"


def test_generic_intel_never_uses_alib(tmp_path):
    # ALIB is an AMD path; an Intel host must not pick it even if acpi_call exists.
    root = str(tmp_path)
    _mk_acpi_call(root)
    intel = dataclasses.replace(GENERIC, vendor="intel")
    b = select_backend(intel, root=root, ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.name != "acpi-alib"


def test_ryzenadj_still_used_when_no_alib(tmp_path):
    # No acpi_call interface -> ALIB unsupported -> ryzenadj remains the fallback.
    b = select_backend(GENERIC, root=str(tmp_path), ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.name == "ryzenadj"


def _mk_amdgpu_powercap(root):
    d = os.path.join(root, "sys/class/hwmon/hwmon0")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "name"), "w") as f:
        f.write("amdgpu")
    with open(os.path.join(d, "power1_cap"), "w") as f:
        f.write("15000000")


def test_amd_does_not_hijack_gpu_power_cap_as_tdp(tmp_path):
    # steamdeck-hwmon matches any power*_cap chip, incl. amdgpu's GPU cap. A non-Deck
    # AMD device must NOT drive the GPU cap as TDP — it falls to ryzenadj.
    root = str(tmp_path)
    _mk_amdgpu_powercap(root)
    b = select_backend(_p("rog_ally_x"), root=root, ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.name != "steamdeck-hwmon"
    assert b.name == "ryzenadj"
