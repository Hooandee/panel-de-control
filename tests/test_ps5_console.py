import os

from ps5.led import Ps5Led, is_animated
from ps5.thermal import HYSTERESIS_C, ThermalGuard, clamp_threshold


class FakeIo:
    def __init__(self, fail=None):
        self.writes = []
        self.fail = fail

    def write(self, path, value):
        self.writes.append((os.path.basename(os.path.dirname(path)), value))
        return self.fail

    def read(self, path):
        return None, None

    def diagnostics(self):
        return {}


def _leds(root, *names):
    for name in names:
        node = os.path.join(root, "sys/class/leds", f"ps5:{name}:indicator")
        os.makedirs(node)
        with open(os.path.join(node, "brightness"), "w") as handle:
            handle.write("0")
    os.makedirs(os.path.join(root, "sys/class/leds", "input2::capslock"), exist_ok=True)


def test_presets_come_from_the_kernel_with_off_first(tmp_path):
    _leds(str(tmp_path), "blue_rich", "off", "pink_breathe")
    assert Ps5Led(root=str(tmp_path), io=FakeIo()).presets() == ["off", "blue_rich", "pink_breathe"]


def test_no_ps5_leds_is_unsupported(tmp_path):
    os.makedirs(tmp_path / "sys/class/leds/input2::capslock")
    assert Ps5Led(root=str(tmp_path), io=FakeIo()).supported is False


def test_apply_lights_the_chosen_preset(tmp_path):
    _leds(str(tmp_path), "off", "blue_rich")
    io = FakeIo()
    assert Ps5Led(root=str(tmp_path), io=io).apply("blue_rich") == {"ok": True, "preset": "blue_rich", "detail": "sent"}
    assert io.writes == [("ps5:blue_rich:indicator", 1)]


def test_unknown_preset_is_refused_without_writing(tmp_path):
    _leds(str(tmp_path), "off")
    io = FakeIo()
    assert Ps5Led(root=str(tmp_path), io=io).apply("sunrise")["detail"] == "unknown_preset"
    assert io.writes == []


def test_replay_switches_off_then_on_because_the_driver_skips_repeats(tmp_path):
    _leds(str(tmp_path), "pink_breathe")
    io = FakeIo()
    Ps5Led(root=str(tmp_path), io=io).replay("pink_breathe")
    assert io.writes == [("ps5:pink_breathe:indicator", 0), ("ps5:pink_breathe:indicator", 1)]


def test_firmware_errors_are_reported(tmp_path):
    _leds(str(tmp_path), "blue_rich")
    assert Ps5Led(root=str(tmp_path), io=FakeIo(fail="errno_19")).apply("blue_rich")["detail"] == "errno_19"


def test_animated_presets_are_recognised():
    assert all(is_animated(name) for name in ("blue_breathe", "zoneb_white_pulse", "blue_white_anim", "sunrise", "blue_to_richblue"))
    assert not any(is_animated(name) for name in ("blue_rich", "off", "purple_white"))


def test_guard_engages_at_threshold_and_releases_after_cooling():
    guard = ThermalGuard()
    assert guard.step(94, threshold=95, guard=True, alarm=False).engage is False
    assert guard.step(95, threshold=95, guard=True, alarm=False).engage is True
    assert guard.step(90, threshold=95, guard=True, alarm=False).release is False
    assert guard.step(95 - HYSTERESIS_C, threshold=95, guard=True, alarm=False).release is True
    assert guard.active is False


def test_alarm_beeps_once_per_episode():
    guard = ThermalGuard()
    assert guard.step(96, threshold=95, guard=False, alarm=True).beep is True
    assert guard.step(97, threshold=95, guard=False, alarm=True).beep is False
    guard.step(80, threshold=95, guard=False, alarm=True)
    assert guard.step(96, threshold=95, guard=False, alarm=True).beep is True


def test_turning_the_guard_off_releases_it():
    guard = ThermalGuard()
    guard.step(99, threshold=95, guard=True, alarm=False)
    assert guard.step(99, threshold=95, guard=False, alarm=False).release is True


def test_unknown_temperature_changes_nothing():
    guard = ThermalGuard()
    guard.step(99, threshold=95, guard=True, alarm=False)
    step = guard.step(None, threshold=95, guard=True, alarm=False)
    assert (step.engage, step.release, guard.active) == (False, False, True)


def test_threshold_is_clamped():
    assert clamp_threshold(50) == 80 and clamp_threshold(120) == 100
