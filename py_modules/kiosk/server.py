"""Loopback HTTP server for the bottom screen: game art plus the same RPCs Decky exposes."""

import asyncio
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

TOKEN_HEADER = "x-pdc-kiosk"
MAX_BODY_BYTES = 1 << 20
KEEPALIVE_IDLE_S = 30.0
READ_TIMEOUT_S = 10.0

Dispatch = Callable[[str, list], Awaitable[Any]]
ArtResolver = Callable[[str, str], "tuple[str, str] | None"]


@dataclass
class Response:
    status: int
    body: bytes
    content_type: str = "application/json"
    headers: dict = field(default_factory=dict)


def _json(status: int, payload: dict) -> Response:
    return Response(status, json.dumps(payload).encode())


class KioskServer:
    def __init__(
        self,
        dispatch: Dispatch,
        allowed_methods: Iterable[str],
        on_error: Callable[[str, str], None] = lambda _method, _error: None,
        art: ArtResolver = lambda _appid, _kind: None,
    ):
        self.dispatch = dispatch
        self.allowed = frozenset(allowed_methods)
        self.on_error = on_error
        self.art = art
        self.token = secrets.token_urlsafe(24)
        self.port: int | None = None
        self._server: asyncio.AbstractServer | None = None
        # Per-method call counts and total seconds, for "what does the bottom screen cost".
        self.calls: dict[str, list[float]] = {}
        self._clients: set[asyncio.StreamWriter] = set()

    @property
    def url(self) -> str | None:
        if self.port is None:
            return None
        return f"http://127.0.0.1:{self.port}/?k={self.token}"

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            # Idle keep-alive connections would otherwise hold wait_closed() open.
            for writer in list(self._clients):
                writer.close()
            await self._server.wait_closed()
        self._server = None
        self.port = None

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        # Keep-alive: the bottom screen polls all the time, and a fresh TCP connection per request
        # costs more than the request under emulation on ARM handhelds.
        self._clients.add(writer)
        try:
            while True:
                try:
                    first = await asyncio.wait_for(reader.readline(), KEEPALIVE_IDLE_S)
                except asyncio.TimeoutError:
                    return
                if not first:
                    return
                try:
                    response, keep = await asyncio.wait_for(self._handle(first, reader), READ_TIMEOUT_S)
                except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, ValueError):
                    response, keep = _json(400, {"error": "bad_request"}), False
                writer.write(self._encode(response, keep))
                await writer.drain()
                if not keep:
                    return
        except ConnectionError:
            pass
        finally:
            self._clients.discard(writer)
            writer.close()

    @staticmethod
    def _encode(response: Response, keep_alive: bool = False) -> bytes:
        reason = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 413: "Payload Too Large",
                  500: "Internal Server Error"}.get(response.status, "OK")
        headers = {
            "Content-Type": response.content_type,
            "Content-Length": str(len(response.body)),
            "Cache-Control": "no-store",
            "Connection": "keep-alive" if keep_alive else "close",
            **response.headers,
        }
        head = f"HTTP/1.1 {response.status} {reason}\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        return head.encode() + b"\r\n" + response.body

    async def _handle(self, first: bytes, reader: asyncio.StreamReader) -> tuple[Response, bool]:
        request_line = first.decode("latin-1").strip()
        method, _, rest = request_line.partition(" ")
        target, _, version = rest.partition(" ")
        path = target.split("?", 1)[0]
        headers: dict[str, str] = {}
        while True:
            line = (await reader.readline()).decode("latin-1")
            if line in ("\r\n", "\n", ""):
                break
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        keep = version.strip() == "HTTP/1.1" and headers.get("connection", "").lower() != "close"
        if method == "GET" and path.startswith("/art/"):
            return self._art(path), keep
        if method == "POST" and path == "/rpc":
            length = int(headers.get("content-length", "0") or 0)
            if length > MAX_BODY_BYTES:
                return _json(413, {"error": "too_large"}), False
            body = await reader.readexactly(length) if length else b""
            return await self._rpc(headers, body), keep
        return _json(404, {"error": "not_found"}), keep

    def _art(self, path: str) -> Response:
        parts = path.split("/")
        found = self.art(parts[2], parts[3]) if len(parts) == 4 else None
        if found is None:
            return _json(404, {"error": "not_found"})
        file_path, content_type = found
        try:
            with open(file_path, "rb") as handle:
                return Response(200, handle.read(), content_type, {"Cache-Control": "max-age=3600"})
        except OSError:
            return _json(404, {"error": "not_found"})

    async def _rpc(self, headers: dict[str, str], body: bytes) -> Response:
        presented = headers.get(TOKEN_HEADER, "").encode("latin-1", "replace")
        if not hmac.compare_digest(presented, self.token.encode()):
            return _json(403, {"error": "forbidden"})
        try:
            request = json.loads(body or b"{}")
            name = request["method"]
            args = request.get("args", [])
        except (ValueError, KeyError, TypeError):
            return _json(400, {"error": "bad_request"})
        if not isinstance(name, str) or not isinstance(args, list):
            return _json(400, {"error": "bad_request"})
        if name not in self.allowed:
            return _json(404, {"error": "unknown_method"})
        started = time.monotonic()
        try:
            result = await self.dispatch(name, args)
        except Exception as exc:  # noqa: BLE001
            self.on_error(name, f"{type(exc).__name__}: {exc}")
            return _json(500, {"error": type(exc).__name__})
        finally:
            tally = self.calls.setdefault(name, [0, 0.0])
            tally[0] += 1
            tally[1] += time.monotonic() - started
        try:
            return _json(200, {"result": result})
        except (TypeError, ValueError) as exc:
            self.on_error(name, f"unserializable result: {exc}")
            return _json(500, {"error": "unserializable"})
