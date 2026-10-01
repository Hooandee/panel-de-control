import os

from fans.armada import ArmadaFanBackend, powerd_min_duty, powerd_present


def _write(root, rel, value):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(str(value))


def _read(root, rel):
    with open(os.path.join(root, rel)) as handle:
        return handle.read().strip()


class FakeControl:
    def __init__(self, stop_ok=True, start_ok=True, guard_ok=True):
        self.calls = []
        self.stop_ok, self.start_ok, self.guard_ok = stop_ok, start_ok, guard_ok

    def start_guard(self):
        self.calls.append("guard+")
        return self.guard_ok

    def stop_guard(self):
        self.calls.append("guard-")
        return True

    def stop_powerd(self):
        self.calls.append("stop")
        return self.stop_ok

    def start_powerd(self):
        self.calls.append("start")
        return self.start_ok


def _thor(tmp_path):
    root = str(tmp_path)
    fan = "sys/class/hwmon/hwmon41"
    _write(root, f"{fan}/name", "pwmfan")
    _write(root, f"{fan}/pwm1", 51)
    _write(root, f"{fan}/pwm1_enable", 3)
    _write(root, f"{fan}/fan1_input", 2120)
    _write(root, "usr/lib/systemd/system/armada-powerd.service", "[Service]\n")
    _write(root, "usr/share/armada/power-profiles.conf", "[fan]\nmin_pwm=51\nmax_pwm=255\n")
    return root, fan


CURVE = [[40, 0], [60, 128], [80, 255]]


def test_presence_and_floor_come_from_armada(tmp_path):
    root, _ = _thor(tmp_path)
    assert powerd_present(root) is True
    assert powerd_min_duty(root) == 51
    assert powerd_present(str(tmp_path / "none")) is False


def test_curve_takes_the_fan_only_after_guarding_and_stopping_powerd(tmp_path):
    root, fan = _thor(tmp_path)
    control = FakeControl()
    backend = ArmadaFanBackend(temp_fn=lambda: 60.0, root=root, control=control)
    result = backend.apply_curve_all(CURVE)
    backend.stop()
    assert result["ok"] is True
    assert control.calls == ["guard+", "stop"]
    assert _read(root, f"{fan}/pwm1_enable") == "1"
    assert int(_read(root, f"{fan}/pwm1")) == 128


def test_low_curve_points_never_go_below_armadas_floor(tmp_path):
    root, fan = _thor(tmp_path)
    backend = ArmadaFanBackend(temp_fn=lambda: 30.0, root=root, control=FakeControl())
    backend.apply_curve_all(CURVE)
    backend.stop()
    assert int(_read(root, f"{fan}/pwm1")) == 51


def test_release_restores_mode_and_hands_back_to_powerd(tmp_path):
    root, fan = _thor(tmp_path)
    control = FakeControl()
    backend = ArmadaFanBackend(temp_fn=lambda: 60.0, root=root, control=control)
    backend.apply_curve_all(CURVE)
    result = backend.set_auto()
    assert result["ok"] is True
    assert _read(root, f"{fan}/pwm1_enable") == "3"
    assert control.calls == ["guard+", "stop", "start", "guard-"]


def test_powerd_that_will_not_stop_is_never_fought(tmp_path):
    root, fan = _thor(tmp_path)
    control = FakeControl(stop_ok=False)
    backend = ArmadaFanBackend(temp_fn=lambda: 60.0, root=root, control=control)
    result = backend.apply_curve_all(CURVE)
    backend.stop()
    assert result["ok"] is False
    assert control.calls == ["guard+", "stop", "guard-"]
    assert _read(root, f"{fan}/pwm1_enable") == "3"


def test_failed_handback_keeps_the_guard_alive(tmp_path):
    root, _ = _thor(tmp_path)
    control = FakeControl(start_ok=False)
    backend = ArmadaFanBackend(temp_fn=lambda: 60.0, root=root, control=control)
    backend.apply_curve_all(CURVE)
    result = backend.set_auto()
    assert result["ok"] is False
    assert "guard-" not in control.calls[2:]


def test_arm_devices_with_armada_select_the_handoff_backend(tmp_path):
    from types import SimpleNamespace

    from fans.control import select_fan_backend

    root, _ = _thor(tmp_path)
    arm = SimpleNamespace(key="ayn_thor", arch="arm")
    x86 = SimpleNamespace(key="generic", arch="x86")
    assert select_fan_backend(arm, root=root).name == "armada-pwm"
    assert select_fan_backend(x86, root=root).name == "generic-pwm"


def test_systemd_control_masks_while_owning_and_unmasks_on_handback(monkeypatch):
    import fans.armada as armada

    calls = []
    monkeypatch.setattr(armada, "_run", lambda argv: calls.append(argv[1:]) or True)
    control = armada.SystemdPowerdControl(pid=4242)
    control.stop_powerd()
    control.start_powerd()
    control.start_guard()
    assert calls[0] == ["mask", "--runtime", "--now", "armada-powerd.service"]
    assert calls[1] == ["unmask", "--runtime", "armada-powerd.service"]
    assert calls[3] == ["start", "armada-powerd.service"]
    guard = " ".join(calls[-1])
    assert "kill -0 4242" in guard
    assert "unmask --runtime armada-powerd.service" in guard
