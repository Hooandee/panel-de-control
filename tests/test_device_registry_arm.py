from device_registry import detect


def _arm_root(tmp_path, compatible=(), model="", soc_family="", soc_machine=""):
    regs = tmp_path / "sys/devices/system/cpu/cpu0/regs/identification"
    regs.mkdir(parents=True)
    (regs / "midr_el1").write_text("0x00000000411fd461\n")
    if compatible or model:
        dt = tmp_path / "proc/device-tree"
        dt.mkdir(parents=True)
        (dt / "compatible").write_bytes(b"".join(c.encode() + b"\0" for c in compatible))
        (dt / "model").write_bytes(model.encode() + b"\0")
    if soc_family or soc_machine:
        soc = tmp_path / "sys/devices/soc0"
        soc.mkdir(parents=True)
        (soc / "family").write_text(soc_family + "\n")
        (soc / "machine").write_text(soc_machine + "\n")
    cpuinfo = tmp_path / "proc"
    cpuinfo.mkdir(exist_ok=True)
    (cpuinfo / "cpuinfo").write_text("vendor_id\t: GenuineIntel\nmodel name\t: Cortex-A510\n")
    return str(tmp_path)


def test_ayn_thor_is_recognised_by_device_tree_even_when_emulation_reports_intel(tmp_path):
    root = _arm_root(
        tmp_path,
        compatible=("ayn,thor", "qcom,qcs8550", "qcom,sm8550"),
        model="AYN Thor",
        soc_family="Snapdragon",
        soc_machine="QCS8550",
    )
    prof = detect(root=root)
    assert prof.key == "ayn_thor"
    assert prof.arch == "arm"
    assert prof.vendor == "qualcomm"
    assert prof.chip == "Snapdragon 8 Gen 2"
    assert prof.is_generic is False
    assert prof.experimental is True


def test_sibling_on_the_same_soc_is_not_mistaken_for_the_thor(tmp_path):
    root = _arm_root(
        tmp_path,
        compatible=("ayn,odin2", "qcom,sm8550"),
        model="AYN Odin 2",
    )
    prof = detect(root=root)
    assert prof.key == "generic_arm"
    assert prof.is_generic is True
    assert prof.display_name == "AYN Odin 2"
    assert prof.chip == "Snapdragon 8 Gen 2"
    assert prof.vendor == "qualcomm"
    assert prof.arch == "arm"


def test_unknown_arm_soc_shows_kernel_soc_name_never_emulated_cpuinfo(tmp_path):
    root = _arm_root(
        tmp_path,
        compatible=("vendor,board", "rockchip,rk3588"),
        model="Some Board",
        soc_family="Rockchip",
        soc_machine="RK3588",
    )
    prof = detect(root=root)
    assert prof.key == "generic_arm"
    assert prof.vendor == "rockchip"
    assert prof.chip == "Rockchip RK3588"


def test_arm_without_device_tree_still_never_becomes_x86_generic(tmp_path):
    prof = detect(root=_arm_root(tmp_path))
    assert prof.key == "generic_arm"
    assert prof.arch == "arm"
    assert prof.vendor != "intel"
    assert prof.display_name


def test_x86_host_keeps_x86_identity(tmp_path):
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc/cpuinfo").write_text("vendor_id\t: AuthenticAMD\nmodel name\t: AMD Ryzen Z1\n")
    prof = detect(product_name="Unknown", root=str(tmp_path))
    assert prof.key == "generic"
    assert prof.arch == "x86"
    assert prof.vendor == "amd"


def test_arm_never_reaches_x86_power_or_gpu_clock_paths(tmp_path):
    from gpu.clock import select_gpu_clock
    from tdp.factory import select_backend

    root = _arm_root(tmp_path, compatible=("ayn,thor", "qcom,sm8550"), model="AYN Thor")
    for name in ("intel-rapl:0", "intel-rapl:0:0"):
        rapl = tmp_path / "sys/class/powercap" / name
        rapl.mkdir(parents=True)
        (rapl / "constraint_0_power_limit_uw").write_text("15000000\n")
    prof = detect(root=root)

    def no_ryzenadj():
        raise AssertionError("ryzenadj must not be resolved on ARM")

    backend = select_backend(prof, root=root, ryzenadj_resolve=no_ryzenadj)
    assert backend.supported is False
    assert backend.probe_trace == ()
    assert select_gpu_clock(prof, root=root)._selection == []
