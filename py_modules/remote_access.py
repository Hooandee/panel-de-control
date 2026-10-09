"""Developer remote access: a key-only SSH server plus a pairing window.

The server is the system's own OpenSSH when Panel runs as root, started with a key-only
configuration of its own on a separate port, so the system's sshd service and its settings are
never touched. Without it, or without root (an unprivileged sandbox), the bundled static dropbear
takes its place and logs only into the account it runs as.
A computer is authorised only after its public key arrives during a short pairing
window and the user accepts its fingerprint on the device itself.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import fcntl
import hashlib
import os
import platform
import pwd
import shutil
import signal
import socket
import struct
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SSH_PORT = 2222
PAIR_PORT = 2223
PAIR_WINDOW_S = 120.0
_MAX_KEY_LINE = 4096
_RESTART_DELAYS_S = (2.0, 5.0, 15.0, 60.0)
_STOP_TIMEOUT_S = 3.0
_KEY_TYPES = frozenset((
    "ssh-ed25519",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
))
_VIRTUAL_IFACE_PREFIXES = ("lo", "tun", "tap", "wg", "docker", "br-", "virbr", "veth", "utun", "dummy")
_SIOCGIFADDR = 0x8915
_SYSTEM_SSHD = ("/usr/bin/sshd", "/usr/sbin/sshd")

Journal = Callable[..., None]


@dataclass(frozen=True)
class PublicKey:
    key_type: str
    blob: bytes
    comment: str

    @property
    def fingerprint(self) -> str:
        digest = base64.b64encode(hashlib.sha256(self.blob).digest()).decode().rstrip("=")
        return f"SHA256:{digest}"

    def authorized_line(self) -> str:
        line = f"{self.key_type} {base64.b64encode(self.blob).decode()}"
        return f"{line} {self.comment}" if self.comment else line


def parse_public_key(line: str) -> PublicKey | None:
    parts = line.strip().split(None, 2)
    if len(parts) < 2 or parts[0] not in _KEY_TYPES:
        return None
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(blob) < 4:
        return None
    (name_len,) = struct.unpack(">I", blob[:4])
    if blob[4:4 + name_len].decode("ascii", "replace") != parts[0]:
        return None
    comment = parts[2].strip() if len(parts) > 2 else ""
    comment = "".join(ch for ch in comment if ch.isprintable())[:80]
    return PublicKey(parts[0], blob, comment)


@dataclass(frozen=True)
class SshServer:
    kind: str
    binary: Path


def system_sshd() -> Path | None:
    """OpenSSH needs root to switch to the account that logs in."""
    if os.geteuid() != 0:
        return None
    return next((Path(path) for path in _SYSTEM_SSHD if os.access(path, os.X_OK)), None)


def binary_arch(machine: str | None = None) -> str | None:
    machine = (machine or platform.machine()).lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    return None


def lan_addresses() -> list[str]:
    """IPv4 of physical interfaces. A VPN (Cloudflare WARP, WireGuard) owns the default
    route on many handhelds, so asking the routing table would return its tunnel
    address, which no computer on the LAN can reach."""
    found: list[str] = []
    try:
        names = [name for _, name in socket.if_nameindex()]
    except OSError:
        return found
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        for name in names:
            if name.startswith(_VIRTUAL_IFACE_PREFIXES):
                continue
            try:
                packed = fcntl.ioctl(probe.fileno(), _SIOCGIFADDR, struct.pack("256s", name[:15].encode()))
            except OSError:
                continue
            found.append(socket.inet_ntoa(packed[20:24]))
    return found


def current_user() -> str | None:
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return None


class RemoteAccess:
    def __init__(self, plugin_dir: str, state_dir: str, journal: Journal, login_user: str | None = None) -> None:
        self._plugin_dir = Path(plugin_dir)
        self._login_user = login_user
        self._state_dir = Path(state_dir)
        self._journal = journal
        self._enabled = False
        self._process: asyncio.subprocess.Process | None = None
        self._supervisor: asyncio.Task | None = None
        self._stderr_tail: deque[str] = deque(maxlen=8)
        self._error: str | None = None
        self._pair_server: asyncio.base_events.Server | None = None
        self._pair_deadline = 0.0
        self._pair_timer: asyncio.Task | None = None
        self._pending: tuple[PublicKey, str, asyncio.Future] | None = None

    @property
    def _authorized_keys(self) -> Path:
        return self._state_dir / "authorized_keys"

    @property
    def _pid_file(self) -> Path:
        return self._state_dir / "server.pid"

    def _host_key(self, server: SshServer) -> Path:
        return self._state_dir / ("ssh_host_ed25519_key" if server.kind == "openssh" else "host_ed25519")

    async def _stop_stale_server(self) -> None:
        """A server left by a previous Panel process that was killed keeps the port, so the
        new one could never listen. Only a process started with our state directory is touched."""
        try:
            pid = int(self._pid_file.read_text().strip())
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        except (OSError, ValueError):
            return
        if str(self._state_dir).encode() not in cmdline:
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
        self._journal("INFO", "stale_server_stopped", pid=pid)
        deadline = time.monotonic() + _STOP_TIMEOUT_S
        while Path(f"/proc/{pid}").exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)

    def server(self) -> SshServer | None:
        sshd = system_sshd()
        if sshd is not None:
            return SshServer("openssh", sshd)
        arch = binary_arch()
        bundled = self._plugin_dir / "bin" / f"dropbear-{arch}" if arch else None
        return SshServer("dropbear", bundled) if bundled is not None and bundled.is_file() else None

    def keys(self) -> list[PublicKey]:
        try:
            lines = self._authorized_keys.read_text().splitlines()
        except OSError:
            return []
        return [key for key in map(parse_public_key, lines) if key is not None]

    def state(self) -> dict:
        pairing = None
        if self._pair_server is not None:
            pending = None
            if self._pending is not None:
                key, peer, _ = self._pending
                pending = {"fingerprint": key.fingerprint, "comment": key.comment, "peer": peer}
            pairing = {
                "port": PAIR_PORT,
                "expires_in": max(0, round(self._pair_deadline - time.monotonic())),
                "pending": pending,
            }
        server = self.server()
        return {
            "supported": server is not None,
            "backend": server.kind if server else None,
            "enabled": self._enabled,
            "running": self._process is not None and self._process.returncode is None,
            "port": SSH_PORT,
            "user": self._login_user or current_user(),
            "addresses": lan_addresses(),
            "keys": [{"fingerprint": k.fingerprint, "comment": k.comment} for k in self.keys()],
            "pairing": pairing,
            "error": self._error,
        }

    def diagnostics(self) -> dict:
        state = self.state()
        return {
            **{key: state[key] for key in ("enabled", "running", "supported", "backend", "user", "error")},
            "paired_keys": len(state["keys"]),
            "pairing_open": state["pairing"] is not None,
            "stderr_tail": list(self._stderr_tail),
        }

    async def set_enabled(self, enabled: bool) -> dict:
        self._enabled = enabled
        if enabled:
            self._error = None
            if self._supervisor is None or self._supervisor.done():
                self._supervisor = asyncio.create_task(self._supervise())
        else:
            await self.close_pairing()
            await self._stop_supervisor()
        self._journal("INFO", "enabled" if enabled else "disabled")
        return self.state()

    async def shutdown(self) -> None:
        await self.close_pairing()
        await self._stop_supervisor()

    async def _stop_supervisor(self) -> None:
        task, self._supervisor = self._supervisor, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await self._stop_process()

    async def _stop_process(self) -> None:
        process, self._process = self._process, None
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), _STOP_TIMEOUT_S)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    async def _supervise(self) -> None:
        failures = 0
        while self._enabled:
            started = time.monotonic()
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001
                self._error = type(error).__name__
                self._journal("ERROR", "start_failed", error=str(error)[:200])
            if not self._enabled:
                return
            failures = 0 if time.monotonic() - started > 60 else failures + 1
            await asyncio.sleep(_RESTART_DELAYS_S[min(failures, len(_RESTART_DELAYS_S) - 1)])

    def _prepare_state_dir(self) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._state_dir, 0o700)
        if self._authorized_keys.exists():
            os.chmod(self._authorized_keys, 0o600)

    async def _run_once(self) -> None:
        server = self.server()
        if server is None:
            self._error = "unsupported"
            raise RuntimeError("no system sshd and no bundled dropbear for this architecture")
        if server.kind == "dropbear" and not os.access(server.binary, os.X_OK):
            os.chmod(server.binary, 0o755)
        self._prepare_state_dir()
        env = {key: value for key, value in os.environ.items() if not key.startswith("LD_")}
        host_key = self._host_key(server)
        if not host_key.exists():
            await self._generate_host_key(server, host_key, env)
        await self._stop_stale_server()
        if server.kind == "openssh":
            config = self._state_dir / "sshd_config"
            config.write_text(self._sshd_config(host_key))
            args = [str(server.binary), "-D", "-e", "-f", str(config)]
        else:
            args = [
                str(server.binary), "dropbear",
                "-F", "-E", "-s",
                "-r", str(host_key),
                "-D", str(self._state_dir),
                "-p", str(SSH_PORT),
                "-P", str(self._pid_file),
                "-K", "30",
            ]
        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._error = None
        self._journal("INFO", "server_started", backend=server.kind, port=SSH_PORT, pid=self._process.pid)
        assert self._process.stderr is not None
        async for raw in self._process.stderr:
            line = raw.decode(errors="replace").strip()
            if line:
                self._stderr_tail.append(line[:200])
        code = await self._process.wait()
        self._process = None
        if self._enabled:
            self._error = f"exited:{code}"
            self._journal("WARNING", "server_exited", code=code, stderr=list(self._stderr_tail)[-3:])

    def _sshd_config(self, host_key: Path) -> str:
        """Keys are read by a root-run command so the paired list can stay in Panel's own
        root-only directory instead of the account's home."""
        cat = shutil.which("cat") or "/bin/cat"
        return "\n".join((
            f"Port {SSH_PORT}",
            f'HostKey "{host_key}"',
            f'PidFile "{self._pid_file}"',
            "AuthorizedKeysFile none",
            f'AuthorizedKeysCommand {cat} "{self._authorized_keys}"',
            "AuthorizedKeysCommandUser root",
            "PubkeyAuthentication yes",
            "PasswordAuthentication no",
            "KbdInteractiveAuthentication no",
            "PermitRootLogin prohibit-password",
            "UsePAM yes",
            "",
        ))

    async def _generate_host_key(self, server: SshServer, host_key: Path, env: dict) -> None:
        """dropbear -R ignores -r and always writes under /etc/dropbear, which is read-only or
        absent in sandboxes, so the key is generated up front for both servers."""
        if server.kind == "openssh":
            keygen = shutil.which("ssh-keygen") or str(server.binary.with_name("ssh-keygen"))
            args = [keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(host_key)]
        else:
            args = [str(server.binary), "dropbearkey", "-t", "ed25519", "-f", str(host_key)]
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        _, stderr = await asyncio.wait_for(process.communicate(), 30)
        if process.returncode != 0:
            raise RuntimeError(f"host key generation failed: {stderr.decode(errors='replace').strip()[:200]}")

    async def open_pairing(self) -> dict:
        if not self._enabled:
            return self.state()
        if self._pair_server is None:
            try:
                self._pair_server = await asyncio.start_server(self._handle_pair, "0.0.0.0", PAIR_PORT)
            except OSError as error:
                self._error = "pair_port_busy"
                self._journal("ERROR", "pairing_failed", error=str(error)[:200])
                return self.state()
            self._journal("INFO", "pairing_opened")
        self._pair_deadline = time.monotonic() + PAIR_WINDOW_S
        if self._pair_timer is None or self._pair_timer.done():
            self._pair_timer = asyncio.create_task(self._expire_pairing())
        return self.state()

    async def _expire_pairing(self) -> None:
        while time.monotonic() < self._pair_deadline:
            await asyncio.sleep(max(0.5, self._pair_deadline - time.monotonic()))
        self._journal("INFO", "pairing_expired")
        await self.close_pairing(cancel_timer=False)

    async def close_pairing(self, cancel_timer: bool = True) -> dict:
        if self._pending is not None:
            _, _, decision = self._pending
            if not decision.done():
                decision.set_result(False)
            self._pending = None
        server, self._pair_server = self._pair_server, None
        if server is not None:
            server.close()
        timer, self._pair_timer = self._pair_timer, None
        if cancel_timer and timer is not None and timer is not asyncio.current_task():
            timer.cancel()
        return self.state()

    async def _handle_pair(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = (writer.get_extra_info("peername") or ("?",))[0]
        try:
            try:
                line = await asyncio.wait_for(reader.readline(), 15)
            except (asyncio.TimeoutError, ValueError):
                return
            key = parse_public_key(line[:_MAX_KEY_LINE].decode(errors="replace"))
            if key is None:
                writer.write(b"error: send one ed25519 or ecdsa public key line\n")
                return
            if self._pending is not None:
                writer.write(b"error: another computer is waiting for approval\n")
                return
            decision: asyncio.Future = asyncio.get_running_loop().create_future()
            self._pending = (key, peer, decision)
            self._journal("INFO", "pairing_request", fingerprint=key.fingerprint, peer=peer)
            writer.write(f"{key.fingerprint}\nwaiting for approval on the device...\n".encode())
            await writer.drain()
            accepted = await decision
            writer.write(b"accepted\n" if accepted else b"rejected\n")
        finally:
            try:
                await writer.drain()
            except ConnectionError:
                pass
            writer.close()

    async def answer_pairing(self, accept: bool) -> dict:
        if self._pending is None:
            return self.state()
        key, peer, decision = self._pending
        self._pending = None
        if accept:
            self._prepare_state_dir()
            known = {k.blob for k in self.keys()}
            if key.blob not in known:
                with open(self._authorized_keys, "a", encoding="utf-8") as handle:
                    handle.write(key.authorized_line() + "\n")
                os.chmod(self._authorized_keys, 0o600)
            self._journal("INFO", "pairing_accepted", fingerprint=key.fingerprint, peer=peer)
        else:
            self._journal("INFO", "pairing_rejected", fingerprint=key.fingerprint, peer=peer)
        if not decision.done():
            decision.set_result(accept)
        if accept:
            await self.close_pairing()
        return self.state()

    def forget_keys(self) -> dict:
        try:
            self._authorized_keys.unlink()
        except FileNotFoundError:
            pass
        self._journal("INFO", "keys_forgotten")
        return self.state()
