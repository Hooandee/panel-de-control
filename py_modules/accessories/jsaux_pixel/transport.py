"""Blocking serial link to the panel. Callers run it off the asyncio loop."""

import fcntl
import os
import select
import termios
import time

from . import codec

_REPLY_BYTES = 9
# An animation id the firmware does not have: it answers with a rejection and leaves the screen
# as it was, so probing never turns on a panel the user switched off.
_PROBE_ANIMATION = 12
_HANDSHAKE = codec.frame(1, codec.Cmd.ANIMATION, bytes((_PROBE_ANIMATION,)))


class TransportError(Exception):
    pass


class Transport:
    def __init__(self, dev: str, baud: int | None = None):
        self.dev = dev
        self.baud = baud if baud is not None else termios.B1000000
        self._fd: int | None = None

    def open(self) -> None:
        try:
            fd = os.open(self.dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as error:
            raise TransportError(f"open {self.dev}: {error.strerror}") from error
        try:
            fcntl.ioctl(fd, termios.TIOCEXCL)
            attrs = termios.tcgetattr(fd)
            attrs[0] = termios.IGNPAR
            attrs[1] = 0
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[3] = 0
            attrs[4] = attrs[5] = self.baud
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except OSError as error:
            os.close(fd)
            raise TransportError(f"configure {self.dev}: {error.strerror}") from error
        self._fd = fd

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None

    @property
    def is_open(self) -> bool:
        return self._fd is not None

    def send(self, data: bytes) -> None:
        fd = self._require()
        try:
            termios.tcflush(fd, termios.TCIFLUSH)
            view = memoryview(data)
            while view:
                select.select([], [fd], [], 1.0)
                written = os.write(fd, view)
                view = view[written:]
        except OSError as error:
            self.close()
            raise TransportError(f"write {self.dev}: {error.strerror}") from error

    def request(self, data: bytes, timeout: float) -> bytes | None:
        self.send(data)
        fd = self._require()
        deadline = time.monotonic() + timeout
        reply = b""
        try:
            while len(reply) < _REPLY_BYTES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                readable, _, _ = select.select([fd], [], [], remaining)
                if readable:
                    chunk = os.read(fd, 64)
                    if not chunk:
                        raise TransportError(f"{self.dev} closed")
                    reply += chunk
        except OSError as error:
            self.close()
            raise TransportError(f"read {self.dev}: {error.strerror}") from error
        return reply

    def _require(self) -> int:
        if self._fd is None:
            raise TransportError("link is not open")
        return self._fd


def handshake(link: Transport, timeout: float = 1.5) -> bool:
    reply = link.request(_HANDSHAKE, timeout)
    return reply is not None and codec.is_reply(reply, 1, codec.Cmd.ANIMATION)
