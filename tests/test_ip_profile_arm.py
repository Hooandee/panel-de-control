from controllers import ip_profile


def test_thor_is_recognised_without_extra_buttons():
    assert ip_profile.is_known_device("ayn_thor") is True
    assert ip_profile.has_extra_buttons("ayn_thor") is False
    caps = ["Gamepad:Button:South", "Gamepad:Button:Guide", "Gamepad:Button:QuickAccess"]
    assert ip_profile.buttons_for("ayn_thor", caps) == []


def test_devices_with_paddles_keep_them():
    assert ip_profile.has_extra_buttons("legion_go_2") is True
    assert ip_profile.has_extra_buttons("generic_arm") is True


def test_odin3_back_paddles_are_m1_and_m2():
    assert ip_profile.is_known_device("ayn_odin3") is True
    assert ip_profile.has_extra_buttons("ayn_odin3") is True
    caps = ["Gamepad:Button:LeftPaddle1", "Gamepad:Button:RightPaddle1", "Gamepad:Button:South"]
    assert ip_profile.buttons_for("ayn_odin3", caps) == [("LeftPaddle1", "M1"), ("RightPaddle1", "M2")]
