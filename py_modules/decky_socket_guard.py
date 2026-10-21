import asyncio
import os
import signal
import sys

_MODULE = "decky_loader.localplatform.localsocket"


def install(kill=os.kill, getppid=os.getppid) -> str:
    # Decky 3.2.x keeps reading the plugin socket after EOF without ever yielding: a stop
    # request then hangs _unload until SIGKILL, and an orphaned plugin grows by GB per minute.
    module = sys.modules.get(_MODULE)
    socket_class = getattr(module, "UnixSocket", None)
    original = getattr(socket_class, "_listen_for_method_call", None)
    if original is None:
        return "absent"
    if getattr(original, "_pdc_eof_guard", False):
        return "installed"
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
            kill(os.getpid(), signal.SIGTERM)

    _listen_for_method_call._pdc_eof_guard = True
    socket_class._listen_for_method_call = _listen_for_method_call
    return "installed"
