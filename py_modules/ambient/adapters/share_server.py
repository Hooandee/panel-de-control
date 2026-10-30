from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import socket
import threading
import time
from collections import deque
from typing import Any, Callable, Optional

_PAGE = os.path.join(os.path.dirname(__file__), "share_page.html")
_MAX_BODY = 64 * 1024
_MAX_DRAIN = 1024 * 1024
_MAX_HEADER_BYTES = 16 * 1024
_MAX_LINKS_PER_SEND = 50
_MAX_PENDING = 200
_MAX_URL = 2048
_CLIENT_TIMEOUT_SEC = 10
SESSION_TTL_SEC = 600
_REASONS = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 413: "Payload Too Large", 429: "Too Many Requests"}
_LINK = re.compile(r"(?:https?://|(?<![\w.@/])(?=[a-z0-9-]+(?:\.[a-z0-9-]+)+/))[^\s<>\"'`]+", re.IGNORECASE)
_TRAILING = ".,;:!?)]}»”"


def extract_links(text: str) -> list[str]:
    """http(s) links in pasted text; a bare `host.tld/path` gains https://. Anything else is ignored."""
    links: list[str] = []
    for match in _LINK.finditer(text):
        link = match.group(0).rstrip(_TRAILING)
        if not link.lower().startswith(("http://", "https://")):
            link = "https://" + link
        if len(link) <= _MAX_URL and link not in links:
            links.append(link)
        if len(links) >= _MAX_LINKS_PER_SEND:
            break
    return links


def lan_address() -> Optional[str]:
    """The address other devices on the network reach this one at. A UDP connect sends nothing."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        address = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    return None if address.startswith(("127.", "0.")) else address


class ShareServer:
    """A phone on the same network sends links to Panel while the QR code is on screen.

    Listens only while a session is open (and never past its time limit), behind a random token in
    the path. It only collects link text: nothing it receives is fetched or opened by the backend.
    """

    def __init__(self, host: str = "0.0.0.0", lan_address: Callable[[], Optional[str]] = lan_address, ttl_sec: float = SESSION_TTL_SEC):
        self._host = host
        self._lan_address = lan_address
        self._ttl = ttl_sec
        self._lock = threading.Lock()
        self._socket: Optional[socket.socket] = None
        self._pending: deque[str] = deque(maxlen=_MAX_PENDING)
        self._page = b""
        self._deadline = 0.0
        self.token = ""

    @property
    def active(self) -> bool:
        with self._lock:
            return self._socket is not None and time.monotonic() < self._deadline

    def start(self, texts: dict[str, str]) -> dict[str, Any]:
        address = self._lan_address()
        if not address:
            return {"error": "no_network"}
        self.stop()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((self._host, 0))
            listener.listen(8)
        except OSError:
            listener.close()
            return {"error": "unavailable"}
        listener.settimeout(0.5)
        with self._lock:
            self.token = secrets.token_urlsafe(16)
            self._socket = listener
            self._deadline = time.monotonic() + self._ttl
            self._pending.clear()
            self._page = _render_page(texts)
        threading.Thread(target=self._accept_loop, args=(listener,), name="ambient-share", daemon=True).start()
        port = listener.getsockname()[1]
        return {"url": f"http://{address}:{port}/s/{self.token}/", "expiresIn": int(self._ttl)}

    def stop(self) -> None:
        with self._lock:
            listener, self._socket = self._socket, None
            self._deadline = 0.0
        if listener:
            listener.close()

    def take(self) -> list[str]:
        with self._lock:
            links = list(self._pending)
            self._pending.clear()
        return links

    def _accept_loop(self, listener: socket.socket) -> None:
        while True:
            with self._lock:
                if self._socket is not listener:
                    return
                expired = time.monotonic() >= self._deadline
            if expired:
                self.stop()
                return
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._handle, args=(client,), name="ambient-share-client", daemon=True).start()

    def _handle(self, client: socket.socket) -> None:
        with client:
            client.settimeout(_CLIENT_TIMEOUT_SEC)
            try:
                request = _read_request(client)
                if request is None:
                    return _send(client, 400)
                method, target, body = request
                self._route(client, method, target.split("?", 1)[0], body)
            except _TooLarge:
                _send(client, 413)
            except (OSError, ValueError):
                return

    def _route(self, client: socket.socket, method: str, path: str, body: bytes) -> None:
        parts = path.split("/")
        if len(parts) != 4 or parts[1] != "s":
            return _send(client, 404)
        if not self.token or not hmac.compare_digest(parts[2], self.token):
            return _send(client, 403)
        if parts[3] == "" and method == "GET":
            return _send(client, 200, self._page, "text/html; charset=utf-8")
        if parts[3] != "add":
            return _send(client, 404)
        if method != "POST":
            return _send(client, 405)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return _send(client, 400)
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str):
            return _send(client, 400)
        links = extract_links(text)
        with self._lock:
            if len(self._pending) + len(links) > _MAX_PENDING:
                return _send(client, 429)
            self._pending.extend(links)
        _send(client, 200, json.dumps({"added": len(links), "links": links}).encode(), "application/json")


class _TooLarge(Exception):
    pass


def _render_page(texts: dict[str, str]) -> bytes:
    safe = {key: str(value)[:300] for key, value in texts.items() if isinstance(key, str) and isinstance(value, (str, int))}
    with open(_PAGE, encoding="utf-8") as handle:
        page = handle.read()
    payload = json.dumps(safe, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return page.replace("__PDC_TEXTS__", payload).encode("utf-8")


def _read_request(client: socket.socket) -> Optional[tuple[str, str, bytes]]:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = client.recv(4096)
        if not chunk:
            return None
        data += chunk
        if len(data) > _MAX_HEADER_BYTES:
            return None
    head, body = data.split(b"\r\n\r\n", 1)
    lines = head.decode("latin-1").split("\r\n")
    request_line = lines[0].split(" ")
    if len(request_line) != 3 or not request_line[2].startswith("HTTP/"):
        return None
    length = 0
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep and name.strip().lower() == "content-length":
            length = int(value.strip())
    if length < 0:
        return None
    if length > _MAX_BODY:
        remaining = min(length, _MAX_DRAIN) - len(body)
        while remaining > 0:
            chunk = client.recv(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
        raise _TooLarge()
    while len(body) < length:
        chunk = client.recv(min(65536, length - len(body)))
        if not chunk:
            return None
        body += chunk
    return request_line[0], request_line[1], body[:length]


def _send(client: socket.socket, code: int, body: bytes = b"", mime: str = "text/plain") -> None:
    head = [
        f"HTTP/1.1 {code} {_REASONS.get(code, 'OK')}",
        f"Content-Type: {mime}",
        f"Content-Length: {len(body)}",
        "Cache-Control: no-store",
        "Referrer-Policy: no-referrer",
        "X-Content-Type-Options: nosniff",
        "Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src data:",
        "Connection: close",
        "",
        "",
    ]
    client.sendall("\r\n".join(head).encode("latin-1") + body)
