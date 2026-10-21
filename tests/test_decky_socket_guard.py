import asyncio
import signal
import sys
import types

import pytest

import decky_socket_guard


class _OriginalSocket:
    def __init__(self):
        self.active = True
        self.on_new_message = None
        self.server_writer = None

    # Verbatim from Decky 3.3.0 localsocket.py: it spins forever at EOF.
    async def _listen_for_method_call(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.server_writer = writer
        while self.active and self.on_new_message:

            def _(task: asyncio.Task[str|None]):
                res = task.result()
                if res is not None:
                    asyncio.create_task(self._write_single_line(writer, res))

            line = await self._read_single_line(reader)
            asyncio.create_task(self.on_new_message(line)).add_done_callback(_)

    async def _read_single_line(self, reader):
        try:
            return (await reader.readuntil()).decode()
        except asyncio.IncompleteReadError as err:
            return err.partial.decode()

    async def _write_single_line(self, writer, message):
        writer.lines.append(message)


@pytest.fixture
def decky_module(monkeypatch):
    module = types.ModuleType(decky_socket_guard._MODULE)
    module.UnixSocket = type("UnixSocket", (_OriginalSocket,), {})
    monkeypatch.setitem(sys.modules, decky_socket_guard._MODULE, module)
    return module


def _listen(socket, data, handled):
    async def on_new_message(line):
        handled.append(line)
        return "ok"

    socket.on_new_message = on_new_message
    writer = types.SimpleNamespace(lines=[])

    async def run():
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        reader.feed_eof()
        await asyncio.wait_for(socket._listen_for_method_call(reader, writer), 1.0)
        for _ in range(3):
            await asyncio.sleep(0)

    asyncio.run(run())
    return writer


def test_listener_leaves_at_eof_instead_of_spinning(decky_module):
    kills = []
    assert decky_socket_guard.install(kill=lambda *a: kills.append(a), getppid=lambda: 100) == "installed"
    socket = decky_module.UnixSocket()
    handled = []

    writer = _listen(socket, b'{"id":1}\n', handled)

    assert handled == ['{"id":1}\n']
    assert writer.lines == ["ok"]
    assert kills == []


def test_orphaned_plugin_shuts_itself_down(decky_module, monkeypatch):
    kills = []
    warnings = []
    log = types.SimpleNamespace(warning=lambda *a: warnings.append(a))
    parents = iter((100, 1, 1))
    decky_socket_guard.install(
        kill=lambda *a: kills.append(a), getppid=lambda: next(parents), log=log,
    )
    monkeypatch.setattr(decky_socket_guard.os, "getpid", lambda: 4242)

    _listen(decky_module.UnixSocket(), b"", [])

    assert kills == [(4242, signal.SIGTERM)]
    assert warnings and "is gone" in warnings[0][0]


def test_install_is_idempotent_and_skips_missing_decky(decky_module, monkeypatch):
    assert decky_socket_guard.install(getppid=lambda: 1) == "installed"
    first = decky_module.UnixSocket._listen_for_method_call
    assert decky_socket_guard.install(getppid=lambda: 1) == "installed"
    assert decky_module.UnixSocket._listen_for_method_call is first

    monkeypatch.delitem(sys.modules, decky_socket_guard._MODULE)
    assert decky_socket_guard.install() == "absent"


def test_unknown_decky_listener_is_left_untouched(decky_module):
    async def newer_listener(self, reader, writer):
        await self.handle_connection(reader, writer)

    decky_module.UnixSocket._listen_for_method_call = newer_listener
    warnings = []
    log = types.SimpleNamespace(warning=lambda *a: warnings.append(a))

    assert decky_socket_guard.install(getppid=lambda: 1, log=log) == "skipped"
    assert "handle_connection" in str(warnings[0])
    assert decky_module.UnixSocket._listen_for_method_call is newer_listener

