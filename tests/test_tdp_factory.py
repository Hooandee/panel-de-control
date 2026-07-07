import dataclasses
import os

from device_profiles import DEVICE_TABLE, GENERIC
from tdp.factory import select_backend


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
        f.write("steamdeck_hwmon")
    with open(os.path.join(d, "power1_cap"), "w") as f:
        f.write("15000000")


_NO_RYZENADJ = lambda: None  # noqa: E731


def test_rog_uses_asus_armoury_firmware_attr(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "asus-armoury")
    b = select_backend(_p("rog_xbox_ally_x"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and "asus-armoury" in b.name


def test_legion_uses_lenovo_firmware_attr(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "lenovo-wmi-other-0")
    b = select_backend(_p("legion_go_2"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and "lenovo-wmi-other" in b.name


def test_msi_uses_msi_firmware_attr(tmp_path):
    root = str(tmp_path)
    _mk_fw(root, "msi-wmi-platform")
    b = select_backend(_p("msi_claw_8_ai_plus"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and "msi-wmi-platform" in b.name


def test_steam_deck_uses_hwmon(tmp_path):
    root = str(tmp_path)
    _mk_hwmon(root)
    b = select_backend(_p("steam_deck_oled"), root=root, ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported and b.name == "steamdeck-hwmon"


def test_falls_back_to_null_when_nothing_present(tmp_path):
    b = select_backend(_p("rog_ally_x"), root=str(tmp_path), ryzenadj_resolve=_NO_RYZENADJ)
    assert b.supported is False and b.name == "unsupported"


def test_generic_amd_uses_ryzenadj_when_present(tmp_path):
    b = select_backend(GENERIC, root=str(tmp_path), ryzenadj_resolve=lambda: "/usr/bin/ryzenadj")
    assert b.supported and b.name == "ryzenadj"


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
