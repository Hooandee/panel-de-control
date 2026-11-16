import socket
import threading
import urllib.request

import pytest

from ambient.adapters.media_server import MediaServer
from ambient.adapters.stream_relay import StreamRelay

# Heads captured from live stations with host names removed.
ICECAST_HEAD = b"HTTP/1.0 200 OK\r\nicy-description: Unspecified description\r\nicy-pub: 1\r\nicy-audio-info: bitrate=56\r\nAccess-Control-Allow-Origin: *\r\nContent-Type: audio/mpeg\r\n\r\n"
SHOUTCAST_HEAD = b"ICY 200 OK\r\nicy-name: Example\r\nicy-br: 128\r\ncontent-type: audio/aacp\r\n\r\n"
BODY = bytes(range(256)) * 8


class Upstream:
    def __init__(self, responses):
        self.responses = responses
        self.paths = []
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(4)
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                client, _ = self.listener.accept()
            except OSError:
                return
            data = client.recv(4096).decode("latin-1")
            path = data.split(" ")[1]
            self.paths.append(path)
            client.sendall(self.responses[path])
            client.close()

    def close(self):
        self.listener.close()


@pytest.fixture
def upstream():
    servers = []

    def make(responses):
        server = Upstream(responses)
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.close()


@pytest.fixture
def relay():
    return StreamRelay(allow_private=True)


def _read(relay, key):
    stream = relay.open(key)
    assert stream is not None
    try:
        return stream.content_type, b"".join(stream.chunks())
    finally:
        stream.close()


def test_plain_http_status_and_content_type(relay, upstream):
    server = upstream({"/stream64.mp3": ICECAST_HEAD + BODY})
    key = relay.register(f"http://127.0.0.1:{server.port}/stream64.mp3")
    assert _read(relay, key) == ("audio/mpeg", BODY)


def test_icy_status_line_is_accepted(relay, upstream):
    server = upstream({"/;": SHOUTCAST_HEAD + BODY})
    key = relay.register(f"http://127.0.0.1:{server.port}/;")
    assert _read(relay, key) == ("audio/aacp", BODY)


def test_redirect_is_followed(relay, upstream):
    server = upstream({
        "/old": b"HTTP/1.1 302 Found\r\nLocation: /live.mp3\r\n\r\n",
        "/live.mp3": ICECAST_HEAD + BODY,
    })
    key = relay.register(f"http://127.0.0.1:{server.port}/old")
    assert _read(relay, key)[1] == BODY
    assert server.paths == ["/old", "/live.mp3"]


def test_error_status_gives_nothing(relay, upstream):
    server = upstream({"/gone": b"HTTP/1.1 404 Not Found\r\n\r\n"})
    key = relay.register(f"http://127.0.0.1:{server.port}/gone")
    assert relay.open(key) is None


def test_private_addresses_are_not_reached_by_default(upstream):
    server = upstream({"/x": ICECAST_HEAD + BODY})
    guarded = StreamRelay()
    key = guarded.register(f"http://127.0.0.1:{server.port}/x")
    assert guarded.open(key) is None
    assert server.paths == []


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "http:///x", "", "http://example.com:notaport/x"])
def test_only_http_urls_register(relay, url):
    assert relay.register(url) is None


def test_unknown_key_opens_nothing(relay):
    assert relay.open("nope") is None


def test_media_server_serves_registered_stream(upstream):
    server = upstream({"/live.mp3": ICECAST_HEAD + BODY})
    media = MediaServer(resolver=lambda _: None, relay=StreamRelay(allow_private=True))
    media.start()
    try:
        url = media.stream_url(f"http://127.0.0.1:{server.port}/live.mp3")
        assert url.startswith(f"http://127.0.0.1:{media.port}/r/{media.token}/")
        with urllib.request.urlopen(url, timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "audio/mpeg"
            assert response.headers["Access-Control-Allow-Origin"] == "https://steamloopback.host"
            assert response.read() == BODY
        wrong = url.replace(media.token, "x" * len(media.token))
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(wrong, timeout=5)
        assert err.value.code == 403
    finally:
        media.stop()
