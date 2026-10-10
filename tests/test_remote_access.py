import asyncio
import base64
import os
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

import remote_access
from remote_access import RemoteAccess, SshServer, binary_arch, parse_public_key


def _key_line(key_type="ssh-ed25519", comment="mac@studio"):
    name = key_type.encode()
    blob = struct.pack(">I", len(name)) + name + struct.pack(">I", 32) + bytes(range(32))
    return f"{key_type} {base64.b64encode(blob).decode()} {comment}".strip()


def test_parses_ed25519_and_matches_ssh_keygen_fingerprint_format():
    key = parse_public_key(_key_line() + "\n")
    assert key is not None
    assert key.comment == "mac@studio"
    assert key.fingerprint.startswith("SHA256:")
    assert "=" not in key.fingerprint
    assert parse_public_key(key.authorized_line()) == key


@pytest.mark.parametrize("line", [
    "",
    "ssh-rsa AAAAB3NzaC1yc2E= x",
    "ssh-ed25519 not-base64!!",
    "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x07ssh-dss").decode(),
    "command=\"rm -rf /\" " + _key_line(),
])
def test_rejects_anything_but_a_plain_supported_key(line):
    assert parse_public_key(line) is None


def test_comment_cannot_inject_extra_lines():
    key = parse_public_key(_key_line(comment="a\x1bb\tc"))
    assert key is not None
    assert "\n" not in key.authorized_line()
    assert "\x1b" not in key.comment


@pytest.mark.parametrize("machine,arch", [
    ("x86_64", "x86_64"), ("AMD64", "x86_64"), ("aarch64", "aarch64"), ("arm64", "aarch64"), ("riscv64", None),
])
def test_binary_arch(machine, arch):
    assert binary_arch(machine) == arch


def _service(tmp_path, journal=None):
    (tmp_path / "plugin" / "bin").mkdir(parents=True)
    events = journal if journal is not None else []
    service = RemoteAccess(
        str(tmp_path / "plugin"), str(tmp_path / "state"),
        lambda level, event, **fields: events.append((level, event, fields)),
    )
    return service, events


def test_unsupported_without_system_sshd_or_bundled_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(remote_access, "system_sshd", lambda: None)
    service, _ = _service(tmp_path)
    assert service.state()["supported"] is False


def test_system_openssh_comes_before_the_bundled_dropbear(tmp_path, monkeypatch):
    service, _ = _service(tmp_path)
    arch = binary_arch()
    if arch is None:
        pytest.skip("no bundled architecture for this host")
    (tmp_path / "plugin" / "bin" / f"dropbear-{arch}").write_text("")
    monkeypatch.setattr(remote_access, "system_sshd", lambda: Path("/usr/bin/sshd"))
    assert service.server() == SshServer("openssh", Path("/usr/bin/sshd"))
    monkeypatch.setattr(remote_access, "system_sshd", lambda: None)
    assert service.server().kind == "dropbear"


def test_system_sshd_needs_root(monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    assert remote_access.system_sshd() is None


def test_openssh_config_is_key_only_and_reads_panels_own_key_list(tmp_path):
    service, _ = _service(tmp_path)
    config = service._sshd_config(tmp_path / "state" / "ssh_host_ed25519_key")
    assert "PasswordAuthentication no" in config
    assert "KbdInteractiveAuthentication no" in config
    assert "AuthorizedKeysFile none" in config
    assert f'"{tmp_path / "state" / "authorized_keys"}"' in config
    assert f"Port {remote_access.SSH_PORT}" in config


def test_pairing_requires_enabled_server(tmp_path):
    service, _ = _service(tmp_path)
    state = asyncio.run(service.open_pairing())
    assert state["pairing"] is None


def _pair_round_trip(tmp_path, accept: bool, monkeypatch):
    service, events = _service(tmp_path)
    monkeypatch.setattr(remote_access, "PAIR_PORT", 0)

    async def scenario():
        service._enabled = True
        await service.open_pairing()
        port = service._pair_server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write((_key_line() + "\n").encode())
        await writer.drain()
        fingerprint = (await reader.readline()).decode().strip()
        await reader.readline()
        for _ in range(50):
            if service.state()["pairing"]["pending"]:
                break
            await asyncio.sleep(0.01)
        pending = service.state()["pairing"]["pending"]
        state = await service.answer_pairing(accept)
        verdict = (await reader.readline()).decode().strip()
        writer.close()
        await service.shutdown()
        return fingerprint, pending, state, verdict

    return asyncio.run(scenario()), service, events


def test_accepted_key_is_authorised_and_window_closes(tmp_path, monkeypatch):
    (fingerprint, pending, state, verdict), service, events = _pair_round_trip(tmp_path, True, monkeypatch)
    assert pending["fingerprint"] == fingerprint
    assert pending["peer"] == "127.0.0.1"
    assert verdict == "accepted"
    assert state["pairing"] is None
    assert [k["fingerprint"] for k in state["keys"]] == [fingerprint]
    assert oct((tmp_path / "state" / "authorized_keys").stat().st_mode & 0o777) == "0o600"
    assert oct((tmp_path / "state").stat().st_mode & 0o777) == "0o700"
    assert ("INFO", "pairing_accepted") in [(level, event) for level, event, _ in events]


def test_rejected_key_is_not_written(tmp_path, monkeypatch):
    (_, _, state, verdict), _, events = _pair_round_trip(tmp_path, False, monkeypatch)
    assert verdict == "rejected"
    assert state["keys"] == []
    assert not (tmp_path / "state" / "authorized_keys").exists()
    assert "pairing_rejected" in [event for _, event, _ in events]


def test_forget_keys(tmp_path, monkeypatch):
    _, service, _ = _pair_round_trip(tmp_path, True, monkeypatch)
    assert service.forget_keys()["keys"] == []


def test_disabling_closes_the_pairing_window(tmp_path, monkeypatch):
    service, _ = _service(tmp_path)
    monkeypatch.setattr(remote_access, "PAIR_PORT", 0)

    async def scenario():
        service._enabled = True
        await service.open_pairing()
        return await service.set_enabled(False)

    state = asyncio.run(scenario())
    assert state["pairing"] is None
    assert state["enabled"] is False


@pytest.mark.skipif(not os.path.isdir("/proc/self"), reason="needs procfs")
def test_stale_server_from_a_killed_panel_is_stopped_but_strangers_are_not(tmp_path):
    service, events = _service(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    ours = subprocess.Popen([shutil.which("sh"), "-c", "sleep 30", str(state / "sshd_config")])
    stranger = subprocess.Popen([shutil.which("sleep"), "30"])
    try:
        (state / "server.pid").write_text(f"{stranger.pid}\n")
        asyncio.run(service._stop_stale_server())
        assert stranger.poll() is None
        (state / "server.pid").write_text(f"{ours.pid}\n")
        asyncio.run(service._stop_stale_server())
        assert ours.wait(3) != 0
        assert any(event == "stale_server_stopped" for _, event, _ in events)
    finally:
        for process in (ours, stranger):
            process.kill()
            process.wait()


def test_suggests_the_console_user_when_running_as_root(tmp_path):
    service = RemoteAccess(str(tmp_path / "plugin"), str(tmp_path / "state"), lambda *a, **k: None, login_user="deck")
    assert service.state()["user"] == "deck"
