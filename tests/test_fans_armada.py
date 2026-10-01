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
        self.running = True
        self.beats = 0

    def beat(self):
        self.beats += 1

    def start_guard(self):
        self.calls.append("guard+")
        return self.guard_ok

    def stop_guard(self):
        self.calls.append("guard-")
        return True

    def powerd_active(self):
        return self.running

    def stop_powerd(self):
        self.calls.append("stop")
        if self.stop_ok:
            self.running = False
        return self.stop_ok

    def start_powerd(self):
        self.calls.append("start")
        if self.start_ok:
            self.running = True
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
    assert control.calls == ["guard+", "stop", "start", "guard-"]
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

    def fake_run(argv):
        calls.append(argv[1:])
        return True, "inactive" if argv[1:2] == ["is-active"] else ""

    monkeypatch.setattr(armada, "_run", fake_run)
    control = armada.SystemdPowerdControl(pid=4242, heartbeat="/nonexistent/beat")
    assert control.stop_powerd() is True
    control.start_powerd()
    control.start_guard()
    assert calls[0] == ["mask", "--runtime", "--now", "armada-powerd.service"]
    assert ["unmask", "--runtime", "armada-powerd.service"] in calls
    assert ["start", "armada-powerd.service"] in calls
    guard = " ".join(calls[-1])
    assert "--unit=pdc-armada-fan-guard-4242" in guard
    assert "kill -0 4242" in guard
    assert "stat -c %Y /nonexistent/beat" in guard
    assert "unmask --runtime armada-powerd.service" in guard


def test_missing_temperature_hands_the_fan_back_and_retakes_it_later(tmp_path):
    root, fan = _thor(tmp_path)
    reading = {"value": 60.0}
    control = FakeControl()
    backend = ArmadaFanBackend(temp_fn=lambda: reading["value"], root=root, control=control)
    backend.apply_curve_all(CURVE)
    backend.stop()
    reading["value"] = None
    backend._apply_once()
    assert control.running is True
    assert _read(root, f"{fan}/pwm1_enable") == "3"
    reading["value"] = 60.0
    assert backend._apply_once() is True
    assert control.running is False
    assert _read(root, f"{fan}/pwm1_enable") == "1"


def test_a_daemon_that_came_back_is_taken_again(tmp_path):
    root, _ = _thor(tmp_path)
    now = {"t": 0.0}
    control = FakeControl()
    backend = ArmadaFanBackend(temp_fn=lambda: 60.0, root=root, control=control,
                               clock=lambda: now["t"])
    backend.apply_curve_all(CURVE)
    backend.stop()
    control.running = True
    now["t"] = 11.0
    backend._apply_once()
    assert control.running is False
    assert control.calls.count("stop") == 2
    assert control.beats >= 2
