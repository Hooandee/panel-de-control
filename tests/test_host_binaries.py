import os

import device_tree
import user_session


def _host(tmp_path, *names):
    for name in names:
        path = tmp_path / "usr/bin" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n")
        path.chmod(0o755)
    return str(tmp_path)


def test_emulated_plugin_runs_the_host_binary_when_it_exists(tmp_path, monkeypatch):
    host = _host(tmp_path, "pactl")
    monkeypatch.setattr(device_tree, "runs_emulated", lambda: True)
    assert device_tree.host_binary("/usr/bin/pactl", host_root=host) == os.path.join(host, "usr/bin/pactl")


def test_emulated_plugin_keeps_binaries_only_the_emulator_ships(tmp_path, monkeypatch):
    host = _host(tmp_path, "pactl")
    monkeypatch.setattr(device_tree, "runs_emulated", lambda: True)
    assert device_tree.host_binary("/usr/bin/pw-link", host_root=host) == "/usr/bin/pw-link"
    assert device_tree.host_binary("pactl", host_root=host) == "pactl"


def test_native_plugin_never_rewrites_paths(tmp_path, monkeypatch):
    host = _host(tmp_path, "pactl")
    monkeypatch.setattr(device_tree, "runs_emulated", lambda: False)
    assert device_tree.host_binary("/usr/bin/pactl", host_root=host) == "/usr/bin/pactl"


def test_session_commands_use_the_host_binary_when_emulated(monkeypatch):
    monkeypatch.setattr(user_session, "host_binary", lambda path: "/proc/self/root" + path)
    session = user_session.UserSession(os.getuid(), f"/run/user/{os.getuid()}", "deck")
    cmd, _env, _identity = user_session.spawn_args(
        session, ["pactl", "info"], resolve=lambda name: f"/usr/bin/{name}")
    assert cmd == ["/proc/self/root/usr/bin/pactl", "info"]


def test_detection_needs_an_arm_kernel_and_an_x86_interpreter(monkeypatch):
    device_tree.runs_emulated.cache_clear()
    monkeypatch.setattr(device_tree, "is_arm", lambda root="/": True)
    monkeypatch.setattr(device_tree.platform, "machine", lambda: "x86_64")
    assert device_tree.runs_emulated() is True
    device_tree.runs_emulated.cache_clear()
    monkeypatch.setattr(device_tree.platform, "machine", lambda: "aarch64")
    assert device_tree.runs_emulated() is False
    device_tree.runs_emulated.cache_clear()
    monkeypatch.setattr(device_tree, "is_arm", lambda root="/": False)
    monkeypatch.setattr(device_tree.platform, "machine", lambda: "x86_64")
    assert device_tree.runs_emulated() is False
    device_tree.runs_emulated.cache_clear()


def test_shells_and_interpreters_stay_emulated_so_their_children_resolve_alike(tmp_path, monkeypatch):
    host = _host(tmp_path, "sh", "bash", "python3", "env")
    monkeypatch.setattr(device_tree, "runs_emulated", lambda: True)
    for name in ("sh", "bash", "python3", "env"):
        assert device_tree.host_binary(f"/usr/bin/{name}", host_root=host) == f"/usr/bin/{name}"
