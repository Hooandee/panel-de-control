import hashlib
import io
from collections import namedtuple

import pytest

from upscalers import assets
from upscalers.assets import AssetCache, AssetError
from upscalers.catalog import Asset

PAYLOAD = bytes(range(256)) * 4096


def _asset(urls=("http://mirror-a/file", "http://mirror-b/file"), payload=PAYLOAD):
    return Asset("thing", "thing.bin", hashlib.sha256(payload).hexdigest(), len(payload), urls)


class Response(io.BytesIO):
    def __init__(self, data: bytes, status: int = 200, fail_after: int | None = None):
        super().__init__(data)
        self.status = status
        self.fail_after = fail_after

    def read(self, size=-1):
        if self.fail_after is not None and self.tell() >= self.fail_after:
            raise OSError("connection reset")
        return super().read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    monkeypatch.setattr(assets, "BACKOFF_S", (0, 0, 0))
    monkeypatch.setattr(assets.shutil, "disk_usage", lambda path: namedtuple("U", "total used free")(0, 0, 10**12))


def test_a_dropped_download_resumes_where_it_stopped(tmp_path, monkeypatch):
    asset = _asset()
    calls = []

    def urlopen(request, timeout, context):
        calls.append((request.full_url, request.get_header("Range")))
        if len(calls) == 1:
            return Response(PAYLOAD, fail_after=300_000)
        start = int(request.get_header("Range").split("=")[1].rstrip("-"))
        return Response(PAYLOAD[start:], status=206)

    monkeypatch.setattr(assets.urllib.request, "urlopen", urlopen)
    seen = []
    path = AssetCache(tmp_path).ensure(asset, seen.append, lambda: False)
    assert path.read_bytes() == PAYLOAD
    assert calls[0][1] is None and calls[1][1].startswith("bytes=")
    assert seen[-1] == len(PAYLOAD)


def test_a_server_that_ignores_range_restarts_cleanly(tmp_path, monkeypatch):
    asset = _asset()
    responses = [Response(PAYLOAD, fail_after=300_000), Response(PAYLOAD, status=200)]
    monkeypatch.setattr(assets.urllib.request, "urlopen", lambda *a, **k: responses.pop(0))
    assert AssetCache(tmp_path).ensure(asset, lambda n: None, lambda: False).read_bytes() == PAYLOAD


def test_a_bad_mirror_is_skipped_for_the_next(tmp_path, monkeypatch):
    asset = _asset()

    def urlopen(request, timeout, context):
        return Response(b"x" * len(PAYLOAD) if "mirror-a" in request.full_url else PAYLOAD)

    monkeypatch.setattr(assets.urllib.request, "urlopen", urlopen)
    assert AssetCache(tmp_path).ensure(asset, lambda n: None, lambda: False).read_bytes() == PAYLOAD


def test_gives_up_after_retries_and_keeps_the_part_for_next_time(tmp_path, monkeypatch):
    asset = _asset(urls=("http://only/file",))
    attempts = []

    def urlopen(request, timeout, context):
        attempts.append(request.get_header("Range"))
        return Response(PAYLOAD, fail_after=100_000 * len(attempts))

    monkeypatch.setattr(assets.urllib.request, "urlopen", urlopen)
    with pytest.raises(AssetError) as error:
        AssetCache(tmp_path).ensure(asset, lambda n: None, lambda: False)
    assert error.value.code == "download_failed"
    assert len(attempts) == assets.RETRIES
    assert AssetCache(tmp_path).partial(asset).stat().st_size > 0


def test_refuses_to_start_without_room_for_it(tmp_path, monkeypatch):
    asset = _asset()
    monkeypatch.setattr(assets.shutil, "disk_usage", lambda path: namedtuple("U", "total used free")(0, 0, 1000))
    monkeypatch.setattr(assets.urllib.request, "urlopen", lambda *a, **k: pytest.fail("must not download"))
    with pytest.raises(AssetError) as error:
        AssetCache(tmp_path).ensure(asset, lambda n: None, lambda: False)
    assert error.value.code == "no_space"


def test_cancel_stops_the_download(tmp_path, monkeypatch):
    asset = _asset()
    monkeypatch.setattr(assets.urllib.request, "urlopen", lambda *a, **k: Response(PAYLOAD))
    with pytest.raises(AssetError) as error:
        AssetCache(tmp_path).ensure(asset, lambda n: None, lambda: True)
    assert error.value.code == "cancelled"
