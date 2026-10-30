from __future__ import annotations

import hmac
import os
import re
import secrets
import socket
import threading
import urllib.parse
from typing import Callable, Optional

from ..core.media_types import mime_type

Resolver = Callable[[str], Optional[str]]

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_CHUNK = 256 * 1024
_MAX_HEADER_BYTES = 16 * 1024
_CLIENT_TIMEOUT_SEC = 30
_PAGE_FILES = {
    "player.html": (os.path.join(os.path.dirname(__file__), "video_page.html"), "text/html; charset=utf-8", "no-store"),
    "hls.js": (os.path.join(os.path.dirname(__file__), "vendor", "hls.min.js"), "application/javascript", "private, max-age=86400"),
}
_VIDEO_PAGE_NAME = "player.html"
_REASONS = {200: "OK", 206: "Partial Content", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 416: "Range Not Satisfiable"}
# Big Picture's document origin; lets canvas and createImageBitmap read served images.
STEAM_UI_ORIGIN = "https://steamloopback.host"


class MediaServer:
    """Serves indexed media to the Steam client, which cannot open arbitrary disk paths.

    Loopback only, a per-session token in the path, and only ids the resolver maps to a
    guarded real path. Built on plain sockets: Decky's bundled Python does not ship
    `http.server` on every release.
    """

    def __init__(self, resolver: Resolver):
        self._resolver = resolver
        self.token = secrets.token_urlsafe(24)
        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stopping = threading.Event()

    @property
    def port(self) -> Optional[int]:
        return self._socket.getsockname()[1] if self._socket else None

    def start(self) -> int:
        if self._socket:
            return self.port or 0
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        listener.settimeout(0.5)
        self._stopping.clear()
        self._socket = listener
        self._thread = threading.Thread(target=self._accept_loop, name="ambient-media", daemon=True)
        self._thread.start()
        return self.port or 0

    def stop(self) -> None:
        listener, self._socket = self._socket, None
        self._stopping.set()
        if listener:
            listener.close()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def url_for(self, media_id: str) -> Optional[str]:
        if not self._socket:
            return None
        return f"http://127.0.0.1:{self.port}/m/{self.token}/{urllib.parse.quote(media_id, safe='')}"

    def video_page_url(self) -> Optional[str]:
        """Page for Steam's native video window. YouTube refuses embeds without an http(s) referrer."""
        if not self._socket:
            return None
        return f"http://127.0.0.1:{self.port}/v/{self.token}/{_VIDEO_PAGE_NAME}"

    def _accept_loop(self) -> None:
        listener = self._socket
        while listener and not self._stopping.is_set():
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._handle, args=(client,), name="ambient-media-client", daemon=True).start()

    def _handle(self, client: socket.socket) -> None:
        with client:
            client.settimeout(_CLIENT_TIMEOUT_SEC)
            try:
                request = _read_request(client)
                if request is None:
                    return _send_status(client, 400)
                method, target, headers = request
                if method not in ("GET", "HEAD"):
                    return _send_status(client, 405)
                self._serve(client, target, headers, send_body=method == "GET")
            except (OSError, ValueError):
                return

    def _serve(self, client: socket.socket, target: str, headers: dict[str, str], send_body: bool) -> None:
        parts = target.split("?", 1)[0].split("/")
        if len(parts) != 4 or parts[1] not in ("m", "v"):
            return _send_status(client, 404)
        if not hmac.compare_digest(parts[2], self.token):
            return _send_status(client, 403)
        if parts[1] == "v":
            return _serve_page(client, parts[3], send_body)
        path = self._resolver(urllib.parse.unquote(parts[3]))
        mime = mime_type(path) if path else None
        if not path or not mime:
            return _send_status(client, 404)
        try:
            handle = open(path, "rb")
        except OSError:
            return _send_status(client, 404)
        with handle:
            size = os.fstat(handle.fileno()).st_size
            span = _parse_range(headers.get("range"), size)
            if span == "invalid":
                return _send_head(client, 416, {"Content-Range": f"bytes */{size}", "Content-Length": "0"})
            start, end = span if span else (0, size - 1)
            length = max(0, end - start + 1)
            head = {
                "Content-Type": mime,
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Cache-Control": "private, max-age=3600",
                "Access-Control-Allow-Origin": STEAM_UI_ORIGIN,
            }
            if span:
                head["Content-Range"] = f"bytes {start}-{end}/{size}"
            _send_head(client, 206 if span else 200, head)
            if not send_body or length == 0:
                return
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(_CHUNK, remaining))
                if not chunk:
                    break
                client.sendall(chunk)
                remaining -= len(chunk)


def _read_request(client: socket.socket) -> Optional[tuple[str, str, dict[str, str]]]:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = client.recv(4096)
        if not chunk:
            return None
        data += chunk
        if len(data) > _MAX_HEADER_BYTES:
            return None
    lines = data.split(b"\r\n\r\n", 1)[0].decode("latin-1").split("\r\n")
    request_line = lines[0].split(" ")
    if len(request_line) != 3 or not request_line[2].startswith("HTTP/"):
        return None
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    return request_line[0], request_line[1], headers


def _send_head(client: socket.socket, code: int, headers: dict[str, str]) -> None:
    lines = [f"HTTP/1.1 {code} {_REASONS.get(code, 'OK')}"]
    lines += [f"{name}: {value}" for name, value in headers.items()]
    lines += ["Connection: close", "", ""]
    client.sendall("\r\n".join(lines).encode("latin-1"))


def _send_status(client: socket.socket, code: int) -> None:
    _send_head(client, code, {"Content-Length": "0"})


def _serve_page(client: socket.socket, name: str, send_body: bool) -> None:
    entry = _PAGE_FILES.get(name)
    if entry is None:
        return _send_status(client, 404)
    path, mime, cache = entry
    try:
        with open(path, "rb") as handle:
            body = handle.read()
    except OSError:
        return _send_status(client, 404)
    _send_head(client, 200, {"Content-Type": mime, "Content-Length": str(len(body)), "Cache-Control": cache})
    if send_body:
        client.sendall(body)


def _parse_range(header: Optional[str], size: int):
    if not header:
        return None
    match = _RANGE.match(header.strip())
    if not match or size == 0:
        return "invalid"
    first, last = match.groups()
    if first == "" and last == "":
        return "invalid"
    if first == "":
        start, end = max(0, size - int(last)), size - 1
    else:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        return "invalid"
    return start, end
