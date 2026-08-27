import dataclasses
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


def test_falls_back_to_null_when_nothing_present(tmp_path):
    b = select_backend(_p("rog_ally_x"), root=str(tmp_path), ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported is False and b.name == "unsupported"
    assert [item["candidate"] for item in b.probe_trace] == [
        "asus",
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

    exact = select_backend(
        _p("gpd_win_mini_2025"),
        root=root,
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
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

    backend = select_backend(
        _p("gpd_win_mini_2025"),
        root=root,
        ryzenadj_resolve=lambda: "/usr/bin/ryzenadj",
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
