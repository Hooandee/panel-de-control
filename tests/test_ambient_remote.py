import io
import json
import errno
from types import SimpleNamespace

import pytest

from ambient.adapters import remote_sources as rs


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, content_type: str = "application/json", status: int = 200):
        super().__init__(body)
        self.headers = {"Content-Type": content_type}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_for(routes):
    calls = []

    def opener(request, timeout):
        url = request.full_url
        calls.append(url)
        for prefix, response in routes.items():
            if url.startswith(prefix):
                return response() if callable(response) else response
        raise OSError(f"unexpected url {url}")

    opener.calls = calls
    return opener


def test_nasa_keeps_only_images_and_prefers_hd():
    body = json.dumps([
        {"media_type": "image", "url": "https://apod.nasa.gov/a.jpg", "hdurl": "https://apod.nasa.gov/a_hd.jpg", "title": "Nebula", "date": "2026-09-23"},
        {"media_type": "video", "url": "https://youtube.test/x", "title": "Video"},
        {"media_type": "image", "url": "https://apod.nasa.gov/b.jpg", "title": "Moon", "copyright": "Someone", "date": "2026-09-24"},
    ]).encode()
    opener = opener_for({"https://api.nasa.gov/": lambda: FakeResponse(body)})
    items = rs.nasa_images(opener, today="2026-09-24")
    assert [i["url"] for i in items] == ["https://apod.nasa.gov/b.jpg", "https://apod.nasa.gov/a_hd.jpg"]
    assert items[0]["credit"] == "Someone"
    assert "start_date=2026-09-17" in opener.calls[0]



def test_nasa_rate_limit_falls_back_to_official_images_with_credit():
    import urllib.error

    calls = []
    rows = [{"data": [{"media_type": "image", "title": "Nebula", "secondary_creator": "NASA/ESA"}],
             "links": [{"href": "https://images-assets.nasa.gov/large.jpg", "render": "image", "width": 4000},
                       {"href": "https://images-assets.nasa.gov/medium.jpg", "render": "image", "width": 1280}]}]

    def opener(request, timeout):
        calls.append(request.full_url)
        if request.full_url.startswith("https://api.nasa.gov/"):
            raise urllib.error.HTTPError(request.full_url, 429, "quota", {}, None)
        assert request.full_url.startswith("https://images-api.nasa.gov/search?")
        return FakeResponse(json.dumps({"collection": {"items": rows}}).encode())

    assert rs.nasa_images(opener) == [{"url": "https://images-assets.nasa.gov/medium.jpg", "title": "Nebula", "credit": "NASA/ESA"}]
    assert len(calls) == 2


def test_nasa_fallback_filters_invalid_rows_and_bounds_results():
    def valid(n):
        return {"data": [{"media_type": "image", "title": str(n), "center": "JPL"}],
                "links": [{"href": f"https://images-assets.nasa.gov/{n}.jpg", "render": "image", "width": 1280}]}

    rows = [None, {"data": "broken"}, {"data": [{"media_type": "video"}]},
            {"data": [{"media_type": "image"}], "links": [{"href": "http://bad.test/a.jpg", "render": "image"}]},
            valid(0), valid(0), *[valid(n) for n in range(1, 12)]]
    opener = opener_for({"https://api.nasa.gov/": lambda: FakeResponse(b'{}'),
                         "https://images-api.nasa.gov/": lambda: FakeResponse(json.dumps({"collection": {"items": rows}}).encode())})
    items = rs.nasa_images(opener)
    assert len(items) == 8
    assert len({item["url"] for item in items}) == 8
    assert items[0]["credit"] == "NASA/JPL"


def test_nasa_both_sources_unavailable_are_an_error_not_an_empty_catalog():
    with pytest.raises(rs.RemoteError, match="nasa_unavailable"):
        rs.nasa_images(opener_for({}))


def test_bing_builds_absolute_urls():
    body = json.dumps({"images": [{"url": "/th?id=OHR.Lake_1920x1080.jpg", "title": "Lake", "copyright": "© X"}]}).encode()
    opener = opener_for({"https://www.bing.com/": lambda: FakeResponse(body)})
    items = rs.bing_images(opener, market="es-ES")
    assert items == [{"url": "https://www.bing.com/th?id=OHR.Lake_1920x1080.jpg", "title": "Lake", "credit": "© X"}]
    assert "mkt=es-ES" in opener.calls[0]


def test_malformed_feed_yields_empty_list():
    opener = opener_for({"https://www.bing.com/": lambda: FakeResponse(b"not json")})
    assert rs.bing_images(opener, market="en-US") == []


def test_download_caches_by_mime(tmp_path):
    opener = opener_for({"https://img.test/": lambda: FakeResponse(b"JPEGDATA", "image/jpeg")})
    path = rs.download("https://img.test/a", str(tmp_path), opener)
    assert path.endswith(".jpg")
    assert open(path, "rb").read() == b"JPEGDATA"
    assert list(tmp_path.glob("*.tmp")) == []


def test_download_rejects_html(tmp_path):
    opener = opener_for({"https://img.test/": lambda: FakeResponse(b"<html>", "text/html")})
    with pytest.raises(rs.RemoteError, match="unsupported_type"):
        rs.download("https://img.test/a", str(tmp_path), opener)


def test_download_enforces_size_limit(tmp_path):
    opener = opener_for({"https://img.test/": lambda: FakeResponse(b"x" * 50, "image/png")})
    with pytest.raises(rs.RemoteError, match="too_large"):
        rs.download("https://img.test/a", str(tmp_path), opener, max_bytes=10)
    assert list(tmp_path.iterdir()) == []


def test_download_rejects_non_http(tmp_path):
    with pytest.raises(rs.RemoteError, match="invalid_url"):
        rs.download("file:///etc/passwd", str(tmp_path), opener_for({}))


def test_download_rejects_known_length_before_reading_when_disk_is_full(tmp_path, monkeypatch):
    import shutil

    response = FakeResponse(b"JPEGDATA", "image/jpeg")
    response.headers["Content-Length"] = "8"
    monkeypatch.setattr(shutil, "disk_usage", lambda path: SimpleNamespace(free=7))
    with pytest.raises(rs.RemoteError, match="^no_space$"):
        rs.download("https://img.test/a", str(tmp_path), opener_for({"https://img.test/": response}))
    assert response.tell() == 0
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failure", [errno.ENOSPC, errno.EDQUOT])
@pytest.mark.parametrize("stage", ["mkdir", "temporary", "write", "replace"])
def test_download_reports_no_space_and_removes_partial(tmp_path, monkeypatch, failure, stage):
    def fail(*args, **kwargs):
        raise OSError(failure, "full")

    if stage == "mkdir":
        monkeypatch.setattr(rs.os, "makedirs", fail)
    elif stage == "temporary":
        monkeypatch.setattr(rs.tempfile, "mkstemp", fail)
    elif stage == "replace":
        monkeypatch.setattr(rs.os, "replace", fail)
    else:
        fdopen = rs.os.fdopen

        class FullWriter:
            def __init__(self, fd, mode):
                self.out = fdopen(fd, mode)

            def __enter__(self):
                return self

            def write(self, chunk):
                self.out.write(chunk[:2])
                self.out.flush()
                fail()

            def __exit__(self, *args):
                self.out.close()

        monkeypatch.setattr(rs.os, "fdopen", FullWriter)
    opener = opener_for({"https://img.test/": lambda: FakeResponse(b"JPEGDATA", "image/jpeg")})
    with pytest.raises(rs.RemoteError, match="^no_space$"):
        rs.download("https://img.test/a", str(tmp_path), opener)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("content_length", ["8", "invalid", "-1"])
def test_download_accepts_fitting_or_unknown_length(tmp_path, monkeypatch, content_length):
    import shutil

    response = FakeResponse(b"JPEGDATA", "image/jpeg")
    response.headers["Content-Length"] = content_length
    monkeypatch.setattr(shutil, "disk_usage", lambda path: SimpleNamespace(free=8))
    target = rs.download("https://img.test/a", str(tmp_path), opener_for({"https://img.test/": response}))
    assert open(target, "rb").read() == b"JPEGDATA"


def test_nasa_generic_site_logo_uses_the_image_library():
    logo = {"media_type": "image", "url": "https://science.nasa.gov/wp-content/themes/nasa-child/assets/images/nasa-logo@2x.png", "title": "NASA Science"}
    library = {"collection": {"items": [{"data": [{"media_type": "image", "title": "Nebula"}], "links": [{"href": "https://images-assets.nasa.gov/nebula.jpg", "render": "image", "width": 1280}]}]}}
    opener = opener_for({"https://api.nasa.gov/": lambda: FakeResponse(json.dumps([logo] * 8).encode()), "https://images-api.nasa.gov/": lambda: FakeResponse(json.dumps(library).encode())})
    assert rs.nasa_images(opener)[0]["url"] == "https://images-assets.nasa.gov/nebula.jpg"
