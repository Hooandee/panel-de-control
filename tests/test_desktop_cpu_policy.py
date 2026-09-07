import os

from desktop.cpu_policy import DesktopCpuPolicy


def _write(root, name, value):
    directory = os.path.join(root, "sys/firmware/acpi")
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, name), "w") as handle:
        handle.write(value)


def test_platform_profile_requires_all_three_desktop_modes(tmp_path):
    _write(str(tmp_path), "platform_profile", "balanced")
    _write(str(tmp_path), "platform_profile_choices", "low-power balanced performance")
    policy = DesktopCpuPolicy(root=str(tmp_path))
    assert policy.supported is True
    assert policy.state() == "balanced"


def test_set_confirms_readback_and_restore_returns_captured_policy(tmp_path):
    _write(str(tmp_path), "platform_profile", "balanced")
    _write(str(tmp_path), "platform_profile_choices", "low-power balanced performance")
    policy = DesktopCpuPolicy(root=str(tmp_path))
    assert policy.set("low-power")["ok"] is True
    assert policy.state() == "low-power"
    assert policy.restore()["ok"] is True
    assert policy.state() == "balanced"


def test_missing_profile_is_not_supported(tmp_path):
    assert DesktopCpuPolicy(root=str(tmp_path)).supported is False


def test_explicit_durable_target_overrides_session_capture(tmp_path):
    _write(str(tmp_path), "platform_profile", "low-power")
    _write(str(tmp_path), "platform_profile_choices", "low-power balanced performance")
    policy = DesktopCpuPolicy(root=str(tmp_path))

    assert policy.set("low-power")["ok"] is True
    assert policy.restore("balanced")["ok"] is True
    assert policy.state() == "balanced"
