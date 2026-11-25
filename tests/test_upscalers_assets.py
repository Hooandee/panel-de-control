import hashlib
import io
from collections import namedtuple

import pytest

from upscalers import assets
from upscalers.assets import AssetCache, AssetError
from upscalers.catalog import Asset

PAYLOAD = bytes(range(256)) * 4096


def test_7z_members_share_the_verified_unpack_and_keep_exact_paths(tmp_path, monkeypatch):
    cache = AssetCache(tmp_path)
    payload = b"verified archive"
    digest = hashlib.sha256(payload).hexdigest()
    first = Asset("loader", "sdk.7z", digest, len(payload), ("http://invalid",), member="bin/loader.dll")
    second = Asset("provider", "sdk.7z", digest, len(payload), ("http://invalid",), member="bin/provider.dll")
    cache.file(first).parent.mkdir(parents=True)
    cache.file(first).write_bytes(payload)
    unpacked = []
    def unpack(asset):
        unpacked.append(asset.id)
        folder = cache.unpacked(asset)
        (folder / "bin").mkdir(parents=True)
        (folder / "bin/loader.dll").write_bytes(b"loader")
        (folder / "bin/provider.dll").write_bytes(b"provider")
        (folder / ".complete").write_text(digest)
    monkeypatch.setattr(cache, "_unpack", unpack)
    assert cache.ensure(first, lambda _: None, lambda: False).read_bytes() == b"loader"
    assert cache.ensure(second, lambda _: None, lambda: False).read_bytes() == b"provider"
    assert unpacked == ["loader"]


def test_member_rejects_parent_traversal_before_cache_access(tmp_path):
    cache = AssetCache(tmp_path)
    asset = Asset("bad", "sdk.7z", "abc", 1, ("http://invalid",), member="../outside.dll")
    with pytest.raises(AssetError, match="unsafe_archive"):
        cache.ensure(asset, lambda _: None, lambda: False)


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


def _tarball(tmp_path, members):
    import tarfile
    path = tmp_path / "layer.tar.xz"
    with tarfile.open(path, "w:xz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            if data is None:
                info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
                archive.addfile(info)
            else:
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
    payload = path.read_bytes()
    return Asset("layer", "layer.tar.xz", hashlib.sha256(payload).hexdigest(), len(payload), ("http://invalid",), archive=True), payload


def test_a_tarball_unpacks_without_any_system_tool(tmp_path, monkeypatch):
    asset, payload = _tarball(tmp_path, {"lib/layer.so": b"layer", "share/layer.json": b"{}"})
    cache = AssetCache(tmp_path / "cache")
    cache.file(asset).parent.mkdir(parents=True)
    cache.file(asset).write_bytes(payload)
    monkeypatch.setattr(assets.shutil, "which", lambda tool: None)
    unpacked = cache.ensure(asset, lambda _: None, lambda: False)
    assert (unpacked / "lib/layer.so").read_bytes() == b"layer"
    assert (unpacked / "share/layer.json").read_bytes() == b"{}"


@pytest.mark.parametrize("name", ["../escape.so", "/abs.so", "link"])
def test_a_tarball_that_leaves_its_folder_is_rejected(tmp_path, name):
    asset, payload = _tarball(tmp_path, {name: None if name == "link" else b"x"})
    cache = AssetCache(tmp_path / "cache")
    cache.file(asset).parent.mkdir(parents=True)
    cache.file(asset).write_bytes(payload)
    with pytest.raises(AssetError, match="unsafe_archive"):
        cache.ensure(asset, lambda _: None, lambda: False)
    assert not cache.unpacked(asset).exists()


def test_lossless_installs_over_an_unpack_that_only_peeled_the_compression(tmp_path, monkeypatch):
    from upscalers import catalog, lsfg
    from upscalers.service import UpscalerService
    asset, payload = _tarball(tmp_path, {name: name.encode() for name in lsfg.LAYER_FILES})
    asset = Asset(catalog.LSFG_ARCHIVE, asset.filename, asset.sha256, asset.size, asset.urls, archive=True)
    monkeypatch.setitem(catalog.ASSETS, catalog.LSFG_ARCHIVE, asset)
    (tmp_path / "home").mkdir()
    (tmp_path / "proc").mkdir()
    service = UpscalerService(str(tmp_path / "home"), str(tmp_path / "state"), "rdna2", proc=str(tmp_path / "proc"))
    service.cache.file(asset).parent.mkdir(parents=True)
    service.cache.file(asset).write_bytes(payload)
    stale = service.cache.unpacked(asset)
    stale.mkdir()
    (stale / "layer.tar").write_bytes(b"what 7z leaves behind")
    (stale / ".complete").write_text(asset.sha256)
    assert service.lsfg_install()["installed"]
