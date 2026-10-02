"""Loopback HTTP server for the kiosk page: static bundle plus the same RPCs Decky exposes."""

import asyncio
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

TOKEN_HEADER = "x-pdc-kiosk"
MAX_BODY_BYTES = 1 << 20
READ_TIMEOUT_S = 10.0
STATIC_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "kiosk.js": "text/javascript; charset=utf-8",
    "inter.woff2": "font/woff2",
}

Dispatch = Callable[[str, list], Awaitable[Any]]


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
        static_dir: str,
        dispatch: Dispatch,
        allowed_methods: Iterable[str],
        on_error: Callable[[str, str], None] = lambda _method, _error: None,
    ):
        self.static_dir = static_dir
        self.dispatch = dispatch
        self.allowed = frozenset(allowed_methods)
        self.on_error = on_error
        self.token = secrets.token_urlsafe(24)
        self.port: int | None = None
        self._server: asyncio.AbstractServer | None = None

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
            await self._server.wait_closed()
        self._server = None
        self.port = None

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            response = await asyncio.wait_for(self._handle(reader), READ_TIMEOUT_S)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, ValueError):
            response = _json(400, {"error": "bad_request"})
        try:
            writer.write(self._encode(response))
            await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()

    @staticmethod
    def _encode(response: Response) -> bytes:
        reason = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 413: "Payload Too Large",
                  500: "Internal Server Error"}.get(response.status, "OK")
        headers = {
            "Content-Type": response.content_type,
            "Content-Length": str(len(response.body)),
            "Cache-Control": "no-store",
            "Connection": "close",
            **response.headers,
        }
        head = f"HTTP/1.1 {response.status} {reason}\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        return head.encode() + b"\r\n" + response.body

    async def _handle(self, reader: asyncio.StreamReader) -> Response:
        request_line = (await reader.readline()).decode("latin-1").strip()
        method, _, rest = request_line.partition(" ")
        path = rest.partition(" ")[0].split("?", 1)[0]
        headers: dict[str, str] = {}
        while True:
            line = (await reader.readline()).decode("latin-1")
            if line in ("\r\n", "\n", ""):
                break
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        if method == "GET":
            return self._static(path)
        if method == "POST" and path == "/rpc":
            length = int(headers.get("content-length", "0") or 0)
            if length > MAX_BODY_BYTES:
                return _json(413, {"error": "too_large"})
            body = await reader.readexactly(length) if length else b""
            return await self._rpc(headers, body)
        return _json(404, {"error": "not_found"})

    def _static(self, path: str) -> Response:
        name = "index.html" if path in ("", "/") else path.lstrip("/")
        content_type = STATIC_TYPES.get(name)
        if content_type is None:
            return _json(404, {"error": "not_found"})
        try:
            with open(os.path.join(self.static_dir, name), "rb") as handle:
                return Response(200, handle.read(), content_type)
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
        try:
            result = await self.dispatch(name, args)
        except Exception as exc:  # noqa: BLE001
            self.on_error(name, f"{type(exc).__name__}: {exc}")
            return _json(500, {"error": type(exc).__name__})
        try:
            return _json(200, {"result": result})
        except (TypeError, ValueError) as exc:
            self.on_error(name, f"unserializable result: {exc}")
            return _json(500, {"error": "unserializable"})
