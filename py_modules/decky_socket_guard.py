import asyncio
import os
import signal
import sys

_MODULE = "decky_loader.localplatform.localsocket"
# Shape of the listener in Decky 3.0.0 through 3.3.0; any other version is left untouched.
_KNOWN_NAMES = frozenset({
    "_read_single_line", "active", "add_done_callback", "asyncio", "create_task",
    "on_new_message", "server_writer",
})
_KNOWN_VARNAMES = ("self", "reader", "writer", "_", "line")


def install(kill=os.kill, getppid=os.getppid, log=None) -> str:
    # Decky 3.2.x keeps reading the plugin socket after EOF without ever yielding: a stop
    # request then hangs _unload until SIGKILL, and an orphaned plugin grows by GB per minute.
    module = sys.modules.get(_MODULE)
    socket_class = getattr(module, "UnixSocket", None)
    original = getattr(socket_class, "_listen_for_method_call", None)
    if original is None:
        return "absent"
    if getattr(original, "_pdc_eof_guard", False):
        return "installed"
    code = getattr(original, "__code__", None)
    if (
        code is None
        or frozenset(code.co_names) != _KNOWN_NAMES
        or code.co_varnames[: len(_KNOWN_VARNAMES)] != _KNOWN_VARNAMES
    ):
        if log is not None and code is not None:
            log.warning(
                "Decky socket guard skipped: unknown listener names=%s vars=%s",
                sorted(code.co_names), list(code.co_varnames),
            )
        return "skipped"
    loader_pid = getppid()

    async def _listen_for_method_call(self, reader, writer):
        self.server_writer = writer
        while self.active and self.on_new_message:

            def _(task):
                res = task.result()
                if res is not None:
                    asyncio.create_task(self._write_single_line(writer, res))

            line = await self._read_single_line(reader)
            if not line and reader.at_eof():
                break
            asyncio.create_task(self.on_new_message(line)).add_done_callback(_)
        if getppid() != loader_pid:
            if log is not None:
                log.warning(
                    "Decky loader %s is gone (parent now %s); shutting Panel down",
                    loader_pid, getppid(),
                )
            kill(os.getpid(), signal.SIGTERM)

    _listen_for_method_call._pdc_eof_guard = True
    socket_class._listen_for_method_call = _listen_for_method_call
    return "installed"
