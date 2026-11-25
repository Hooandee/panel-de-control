import urllib.error
import urllib.request

import pytest

from ambient.adapters.media_server import MediaServer


@pytest.fixture
def server(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(bytes(range(256)) * 4)
    known = {"local:abc": str(clip)}
    srv = MediaServer(resolver=known.get)
    srv.start()
    yield srv
    srv.stop()


def _get(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    return urllib.request.urlopen(request, timeout=5)


def test_full_file_with_mime(server):
    with _get(server.url_for("local:abc")) as response:
        assert response.status == 200
        assert response.headers["Content-Type"] == "video/mp4"
        assert response.headers["Accept-Ranges"] == "bytes"
        assert response.headers["Access-Control-Allow-Origin"] == "https://steamloopback.host"
        assert len(response.read()) == 1024


def test_range_request(server):
    with _get(server.url_for("local:abc"), {"Range": "bytes=10-19"}) as response:
        assert response.status == 206
        assert response.headers["Content-Range"] == "bytes 10-19/1024"
        assert response.read() == bytes(range(10, 20))


def test_open_ended_and_suffix_ranges(server):
    with _get(server.url_for("local:abc"), {"Range": "bytes=1020-"}) as response:
        assert response.read() == bytes([252, 253, 254, 255])
    with _get(server.url_for("local:abc"), {"Range": "bytes=-2"}) as response:
        assert response.read() == bytes([254, 255])


def test_unsatisfiable_range(server):
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(server.url_for("local:abc"), {"Range": "bytes=5000-6000"})
    assert err.value.code == 416


def test_bad_token_is_forbidden(server):
    url = server.url_for("local:abc").replace(server.token, "x" * len(server.token))
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(url)
    assert err.value.code == 403


def test_unknown_id_is_not_found(server):
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(server.url_for("local:nope"))
    assert err.value.code == 404


def test_binds_loopback_only(server):
    assert server.url_for("local:abc").startswith("http://127.0.0.1:")


def test_stop_is_idempotent(tmp_path):
    srv = MediaServer(resolver=lambda _id: None)
    srv.start()
    srv.stop()
    srv.stop()
    assert srv.url_for("local:abc") is None


def test_video_page_is_served_behind_the_token(server):
    with _get(server.video_page_url()) as response:
        assert response.status == 200
        assert response.headers["Content-Type"].startswith("text/html")
        assert b"iframe_api" in response.read()
    for bad in (server.video_page_url().replace(server.token, "x" * len(server.token)), server.video_page_url().replace("player.html", "other.html")):
        with pytest.raises(urllib.error.HTTPError) as err:
            _get(bad)
        assert err.value.code in (403, 404)


def test_hls_library_is_served_next_to_the_page(server):
    with _get(server.video_page_url().replace("player.html", "hls.js")) as response:
        assert response.headers["Content-Type"] == "application/javascript"
        assert b"Hls" in response.read()
