from __future__ import annotations

import ipaddress
import re
import secrets
import socket
import ssl
import threading
import urllib.parse
from collections import OrderedDict
from typing import Callable, Iterator, Optional

# Steam's UI document is https and Chromium upgrades every http:// media request to https, so a
# station without valid TLS answers media_error_4. Plain-http streams are fetched here instead
# and handed to the player from loopback, which is not upgraded.

_MAX_REDIRECTS = 4
_MAX_REGISTERED = 64
_CONNECT_TIMEOUT_SEC = 8
_READ_TIMEOUT_SEC = 20
_MAX_HEADER_BYTES = 16 * 1024
_CHUNK = 16 * 1024
_STATUS = re.compile(rb"^(?:HTTP/\d(?:\.\d)?|ICY) (\d{3})")
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

HostResolver = Callable[[str, int], list[str]]
Connector = Callable[[str, int, str, bool], socket.socket]


class Upstream:
    def __init__(self, sock: socket.socket, content_type: str, leftover: bytes):
        self._sock = sock
        self.content_type = content_type
        self._leftover = leftover

    def chunks(self) -> Iterator[bytes]:
        if self._leftover:
            first, self._leftover = self._leftover, b""
            yield first
        while True:
            try:
                data = self._sock.recv(_CHUNK)
            except OSError:
                return
            if not data:
                return
            yield data

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def _resolve_host(host: str, port: int) -> list[str]:
    try:
        return list(dict.fromkeys(info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    except OSError:
        return []


def _public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_global


def _connect(address: str, port: int, host: str, secure: bool) -> socket.socket:
    sock = socket.create_connection((address, port), timeout=_CONNECT_TIMEOUT_SEC)
    try:
        if secure:
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        sock.settimeout(_READ_TIMEOUT_SEC)
    except (OSError, ssl.SSLError):
        sock.close()
        raise
    return sock


def _split(url: str) -> Optional[tuple[str, int, str, bool]]:
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    secure = parts.scheme == "https"
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return parts.hostname, port or (443 if secure else 80), path, secure


class StreamRelay:
    """Opens registered http(s) radio streams for the loopback media server.

    Only public addresses are reached, and only URLs the player registered first. The status line
    may be `ICY 200 OK`, which urllib and http.client refuse, so the exchange is done on a socket.
    """

    def __init__(self, resolver: HostResolver = _resolve_host, connector: Connector = _connect, allow_private: bool = False):
        self._resolver = resolver
        self._connector = connector
        self._allow_private = allow_private
        self._known: "OrderedDict[str, str]" = OrderedDict()
        self._lock = threading.Lock()

    def register(self, url: str) -> Optional[str]:
        if not isinstance(url, str) or len(url) > 2048 or _split(url) is None:
            return None
        with self._lock:
            for key, known in self._known.items():
                if known == url:
                    return key
            key = secrets.token_urlsafe(9)
            self._known[key] = url
            while len(self._known) > _MAX_REGISTERED:
                self._known.popitem(last=False)
            return key

    def open(self, key: str) -> Optional[Upstream]:
        with self._lock:
            url = self._known.get(key)
        for _ in range(_MAX_REDIRECTS + 1):
            target = _split(url) if url else None
            if target is None:
                return None
            host, port, path, secure = target
            result = self._request(host, port, path, secure)
            if result is None:
                return None
            status, headers, sock, leftover = result
            if status in (301, 302, 303, 307, 308) and headers.get("location"):
                sock.close()
                url = urllib.parse.urljoin(f"{'https' if secure else 'http'}://{host}:{port}{path}", headers["location"])
                continue
            if status != 200:
                sock.close()
                return None
            return Upstream(sock, headers.get("content-type", "audio/mpeg").split(";")[0].strip() or "audio/mpeg", leftover)
        return None

    def _request(self, host: str, port: int, path: str, secure: bool):
        addresses = self._resolver(host, port)
        if not self._allow_private:
            addresses = [a for a in addresses if _public(a)]
        for address in addresses:
            try:
                sock = self._connector(address, port, host, secure)
            except (OSError, ssl.SSLError):
                continue
            try:
                request = f"GET {path} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: {_USER_AGENT}\r\nAccept: */*\r\nIcy-MetaData: 0\r\nConnection: close\r\n\r\n"
                sock.sendall(request.encode("latin-1", "ignore"))
                head = b""
                while b"\r\n\r\n" not in head:
                    data = sock.recv(4096)
                    if not data or len(head) > _MAX_HEADER_BYTES:
                        raise OSError("no_header")
                    head += data
                raw, _, leftover = head.partition(b"\r\n\r\n")
                lines = raw.split(b"\r\n")
                match = _STATUS.match(lines[0])
                if not match:
                    raise OSError("bad_status")
                headers: dict[str, str] = {}
                for line in lines[1:]:
                    name, sep, value = line.decode("latin-1").partition(":")
                    if sep:
                        headers[name.strip().lower()] = value.strip()
                return int(match.group(1)), headers, sock, leftover
            except OSError:
                sock.close()
        return None
