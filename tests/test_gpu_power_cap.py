import os

from gpu.power_cap import AmdGpuPowerCap


def _write(directory, name, value):
    with open(os.path.join(directory, name), "w") as handle:
        handle.write(str(value))


def _gpu(root, cap=110_000_000):
    directory = os.path.join(root, "sys/class/hwmon/hwmon7")
    os.makedirs(directory)
    _write(directory, "name", "amdgpu")
    _write(directory, "power1_cap", cap)
    _write(directory, "power1_cap_min", 55_000_000)
    _write(directory, "power1_cap_max", 110_000_000)
    _write(directory, "power1_cap_default", 110_000_000)
    return directory


def test_discovers_real_gpu_tgp_bounds(tmp_path):
    _gpu(str(tmp_path))
    cap = AmdGpuPowerCap(root=str(tmp_path))
    assert cap.supported is True
    assert cap.state() == {
        "supported": True,
        "current_w": 110,
        "min_w": 55,
        "max_w": 110,
        "default_w": 110,
    }


def test_set_clamps_and_confirms_readback(tmp_path):
    directory = _gpu(str(tmp_path))
    cap = AmdGpuPowerCap(root=str(tmp_path))
    result = cap.set_watts(200)
    assert result["ok"] is True
    assert result["applied_w"] == 110
    with open(os.path.join(directory, "power1_cap")) as handle:
        assert handle.read() == "110000000"


def test_restore_returns_to_value_captured_before_first_write(tmp_path):
    _gpu(str(tmp_path), cap=80_000_000)
    cap = AmdGpuPowerCap(root=str(tmp_path))
    assert cap.set_watts(55)["ok"] is True
    assert cap.restore()["ok"] is True
    assert cap.state()["current_w"] == 80


def test_absent_capability_never_claims_support(tmp_path):
    assert AmdGpuPowerCap(root=str(tmp_path)).state()["supported"] is False


def test_generic_desktop_does_not_claim_an_uncorrelated_amdgpu_cap(tmp_path):
    _gpu(str(tmp_path))

    assert AmdGpuPowerCap(
        root=str(tmp_path), device_key="generic"
    ).state()["supported"] is False


def test_fremont_keeps_its_validated_amdgpu_cap(tmp_path):
    _gpu(str(tmp_path))

    assert AmdGpuPowerCap(
        root=str(tmp_path), device_key="steam_machine"
    ).state()["supported"] is True


def test_explicit_durable_target_overrides_restart_capture(tmp_path):
    _gpu(str(tmp_path), cap=55_000_000)
    cap = AmdGpuPowerCap(root=str(tmp_path), device_key="steam_machine")

    assert cap.set_watts(55)["ok"] is True
    assert cap.restore(110_000_000)["ok"] is True
    assert cap.state()["current_w"] == 110
