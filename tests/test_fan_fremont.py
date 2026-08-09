import os

from device_registry import detect
from fans.control import select_fan_backend
from fans.fremont import FremontFanBackend
from fans.hwmon import FanReader


CURVE = [(40, 0), (50, 30), (60, 60), (70, 95), (80, 135), (85, 175), (90, 215), (95, 255)]


def _write(directory, name, value):
    with open(os.path.join(directory, name), "w") as handle:
        handle.write(str(value))


def _machine(root):
    system = os.path.join(root, "sys/class/hwmon/hwmon2")
    cpu = os.path.join(root, "sys/class/hwmon/hwmon3")
    gpu = os.path.join(root, "sys/class/hwmon/hwmon7")
    os.makedirs(system)
    os.makedirs(cpu)
    os.makedirs(gpu)
    _write(system, "name", "steamdeck_hwmon")
    _write(system, "fan1_input", 900)
    _write(system, "fan1_target", 0)
    _write(system, "fan1_label", "System Fan")
    _write(cpu, "name", "acpitz")
    _write(cpu, "temp1_input", 50_000)
    _write(gpu, "name", "amdgpu")
    _write(gpu, "fan1_input", 1500)
    _write(gpu, "fan1_label", "GPU Fan")
    _write(gpu, "fan1_max", 4900)
    _write(gpu, "pwm1", 0)
    _write(gpu, "pwm1_enable", 2)
    _write(gpu, "temp1_input", 55_000)
    _write(gpu, "temp1_label", "edge")
    _write(gpu, "temp2_input", 60_000)
    _write(gpu, "temp2_label", "junction")
    _write(gpu, "temp3_input", 58_000)
    _write(gpu, "temp3_label", "mem")
    return system, gpu


def test_factory_selects_fremont_before_steamdeck_backend(tmp_path):
    _machine(str(tmp_path))
    backend = select_fan_backend(detect(product_name="Fremont"), root=str(tmp_path))
    assert isinstance(backend, FremontFanBackend)


def test_reports_validated_max_rpm_and_separate_sensors(tmp_path):
    _machine(str(tmp_path))
    state = FremontFanBackend(root=str(tmp_path)).read_state()
    by_key = {fan["key"]: fan for fan in state["fans"]}
    assert by_key["system"]["max_rpm"] == 1800
    assert by_key["system"]["sensor"] == "CPU / GPU / VRAM"
    assert by_key["system"]["controllable"] is True
    assert by_key["gpu"]["max_rpm"] == 4900
    assert by_key["gpu"]["sensor"] == "GPU junction"
    assert by_key["gpu"]["controllable"] is False


def test_system_curve_uses_hottest_validated_sensor(tmp_path):
    system, gpu = _machine(str(tmp_path))
    backend = FremontFanBackend(root=str(tmp_path))
    assert backend.set_curve("system", CURVE)["ok"] is True
    assert open(os.path.join(system, "fan1_target")).read() == "424"
    assert open(os.path.join(gpu, "pwm1_enable")).read() == "2"


def test_gpu_curve_is_not_claimed_when_fremont_firmware_rejects_manual_mode(tmp_path):
    _system, gpu = _machine(str(tmp_path))
    backend = FremontFanBackend(root=str(tmp_path))
    assert backend.set_curve("gpu", CURVE)["ok"] is False
    assert open(os.path.join(gpu, "pwm1_enable")).read() == "2"


def test_auto_restores_each_channel_without_starting_services(tmp_path):
    system, gpu = _machine(str(tmp_path))
    backend = FremontFanBackend(root=str(tmp_path))
    backend.set_curve("system", CURVE)
    assert backend.set_auto("system")["ok"] is True
    assert open(os.path.join(system, "fan1_target")).read() == "0"
    assert backend.set_auto("gpu")["ok"] is True
    assert open(os.path.join(gpu, "pwm1_enable")).read() == "2"
    assert open(os.path.join(gpu, "pwm1")).read() == "0"


def test_desktop_temperature_monitor_keeps_cpu_gpu_junction_and_vram_separate(tmp_path):
    _machine(str(tmp_path))
    state = FanReader(root=str(tmp_path), desktop=True, device_key="steam_machine").read()
    labels = {item["label"] for item in state["temps"]}
    assert labels == {"CPU", "GPU", "GPU junction", "VRAM"}


def test_monitor_surfaces_each_fan_real_max_rpm(tmp_path):
    _machine(str(tmp_path))
    state = FanReader(root=str(tmp_path), desktop=True, device_key="steam_machine").read()
    assert state["desktop"] is True
    assert state["device_key"] == "steam_machine"
    assert [(fan["channel"], fan["max_rpm"]) for fan in state["fans"]] == [
        ("system", 1800),
        ("gpu", 4900),
    ]


def test_non_desktop_monitor_does_not_publish_desktop_layout_metadata(tmp_path):
    _machine(str(tmp_path))
    state = FanReader(root=str(tmp_path), desktop=False, device_key="steam_machine").read()
    assert "desktop" not in state
    assert all("channel" not in fan for fan in state["fans"])
