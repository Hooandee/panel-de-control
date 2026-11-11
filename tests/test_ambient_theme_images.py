import asyncio
import json
import os
import shutil
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request

import pytest

from ambient.adapters import image_scaler
from ambient.adapters.image_scaler import BUCKETS, ImageScaler, bucket_for, scale_command
from ambient.adapters.library_scan import media_id
from ambient.adapters.media_server import STEAM_UI_ORIGIN
from ambient.adapters.optimizer import OptimizeError
from ambient.adapters import theme_images
from ambient.adapters.theme_images import ThemeImageStore
from ambient.core.image_header import ImageInfo, probe
from ambient.rpc import AmbientRpc
from ambient import service as ambient_service
from ambient.service import AmbientService

FFMPEG = shutil.which("ffmpeg")
VIDA = "hooandee-vida"
DUO = "hooandee-duo"
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None or shutil.which("ffprobe") is None, reason="ffmpeg not installed")


def _exif(orientation):
    tiff = b"MM\x00\x2a" + struct.pack(">I", 8) + struct.pack(">H", 1) + struct.pack(">HHIHH", 0x0112, 3, 1, orientation, 0) + struct.pack(">I", 0)
    body = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(body) + 2) + body


def jpeg_header(width, height, orientation=None):
    """A JPEG that is only a header: enough for the probe, never decoded."""
    sof = b"\x08" + struct.pack(">HH", height, width) + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8" + (_exif(orientation) if orientation else b"") + b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof + b"\xff\xd9"


def _touch(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    _touch(h / "Pictures" / "dunes.jpg", jpeg_header(1200, 800))
    _touch(h / "Pictures" / "huge.jpg", jpeg_header(4000, 3000))
    _touch(h / "Pictures" / "absurd.jpg", jpeg_header(20000, 10000))
    _touch(h / "Pictures" / "broken.jpg", b"JPG")
    _touch(h / "Videos" / "loop.webm", b"WEBM")
    return h


def _service(tmp_path, home):
    return AmbientService(state_dir=str(tmp_path / "state"), cache_dir=str(tmp_path / "cache"), home=str(home))


@pytest.fixture
def service(tmp_path, home):
    svc = _service(tmp_path, home)
    svc._warm_theme_image = lambda *_args: None
    yield svc
    svc.close()


class BlockingRunner:
    """Stands in for ffmpeg: writes the copy, optionally after `gate` opens."""

    def __init__(self, gate=None, code=0):
        self.gate = gate
        self.code = code
        self.runs = []
        self.started = threading.Event()

    def __call__(self, command, _cancel, _timeout):
        self.runs.append(command[-1])
        self.started.set()
        if self.gate is not None:
            self.gate.wait(5)
        if self.code == 0:
            with open(command[-1], "wb") as handle:
                handle.write(b"SCALED")
        return self.code


def _warming_service(tmp_path, home, runner):
    svc = _service(tmp_path, home)
    svc._scaler = ImageScaler(str(tmp_path / "cache" / "theme-images"), find=lambda: "ffmpeg", run=runner)
    return svc


def _listed(images):
    """The listing as each picture's URLs, the shape most assertions care about."""
    return {ref: entry["urls"] for ref, entry in images.items()}


def _ids(service):
    return {m["name"]: m["id"] for m in service.scan()["collections"]["known.images"]}


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read(), response.headers


# Backend registry


def test_a_picked_photo_is_served_with_cors_for_big_picture(service, home):
    ref = _ids(service)["dunes.jpg"]
    picked = service.register_theme_image(ref, VIDA)
    assert picked["ref"] == ref
    assert set(picked["urls"]) == {"1280", "1920", "2560"}
    assert len(set(picked["urls"].values())) == 1, "a picture smaller than every size is served as it is"
    body, headers = _get(picked["urls"]["1280"])
    assert body == (home / "Pictures" / "dunes.jpg").read_bytes()
    assert headers["Access-Control-Allow-Origin"] == STEAM_UI_ORIGIN
    assert service.theme_images() == {ref: {"urls": picked["urls"], "owners": [VIDA]}}
    assert service.diagnostics()["themeImages"] == 1
    event = service.diagnostics()["events"][-1]
    assert (event["kind"], event["detail"]) == ("theme_image", "picked")


def test_a_big_photo_gets_one_url_per_size(service):
    ref = _ids(service)["huge.jpg"]
    urls = service.register_theme_image(ref, VIDA)["urls"]
    assert len(set(urls.values())) == 3
    for bucket, url in urls.items():
        assert f"sized%3A{bucket}%3A" in url


def test_only_scanned_sane_local_photos_can_be_picked(service):
    ids = _ids(service)
    assert service.register_theme_image(ids["loop.webm"], VIDA) == {"error": "not_image"}
    assert service.register_theme_image(ids["absurd.jpg"], VIDA) == {"error": "unsupported_image"}
    assert service.register_theme_image(ids["broken.jpg"], VIDA) == {"error": "unsupported_image"}
    assert service.register_theme_image("local:0000", VIDA) == {"error": "unknown_media"}
    assert service.register_theme_image("remote:https://example.com/a.jpg", VIDA) == {"error": "unknown_media"}
    assert _listed(service.theme_images()) == {}


def test_sized_ids_are_served_only_for_registered_pictures(service):
    ids = _ids(service)
    assert service._serve_path(f"sized:1280:{ids['huge.jpg']}") is None
    service.register_theme_image(ids["dunes.jpg"], VIDA)
    assert service._serve_path(f"sized:999:{ids['dunes.jpg']}") is None
    assert service._serve_path(f"sized:1280:{ids['dunes.jpg']}").endswith("dunes.jpg")


def test_picked_photos_survive_a_restart_without_a_scan_or_the_background(tmp_path, home):
    first = _service(tmp_path, home)
    ref = _ids(first)["dunes.jpg"]
    first.register_theme_image(ref, VIDA)
    first.close()
    second = _service(tmp_path, home)
    try:
        assert second.get_state()["settings"]["background"]["enabled"] is False
        listed = _listed(second.theme_images())
        assert list(listed) == [ref]
        assert _get(listed[ref]["2560"])[0] == (home / "Pictures" / "dunes.jpg").read_bytes()
    finally:
        second.close()


def test_a_photo_that_disappears_has_no_url_and_returns_when_the_file_does(service, home):
    ref = _ids(service)["dunes.jpg"]
    service.register_theme_image(ref, VIDA)
    photo = home / "Pictures" / "dunes.jpg"
    photo.rename(home / "moved.jpg")
    service.scan()
    assert _listed(service.theme_images()) == {}
    (home / "moved.jpg").rename(photo)
    assert list(_listed(service.theme_images())) == [ref]


def test_a_photo_that_becomes_absurd_is_dropped(service, home):
    ref = _ids(service)["dunes.jpg"]
    service.register_theme_image(ref, VIDA)
    (home / "Pictures" / "dunes.jpg").write_bytes(jpeg_header(20000, 10000))
    assert _listed(service.theme_images()) == {}


def test_a_failed_scale_serves_the_original_then_points_at_the_next_larger_size(service, monkeypatch, home):
    ref = _ids(service)["huge.jpg"]
    urls = service.register_theme_image(ref, VIDA)["urls"]
    attempts = []

    def fail(*args):
        attempts.append(args)
        raise OptimizeError("encode_failed")

    monkeypatch.setattr(service._scaler, "scaled", fail)
    assert _get(urls["1920"])[0] == (home / "Pictures" / "huge.jpg").read_bytes()
    listed = _listed(service.theme_images())[ref]
    assert listed == {"1280": urls["1280"], "1920": urls["2560"], "2560": urls["2560"]}
    event = service.diagnostics()["events"][-1]
    assert (event["kind"], event["detail"]) == ("theme_image", "scale:encode_failed")
    _get(urls["1920"])
    assert len(attempts) == 1, "a recent failure is not retried on every request"


def test_every_size_failing_falls_back_to_the_original(service, monkeypatch):
    ref = _ids(service)["huge.jpg"]
    service.register_theme_image(ref, VIDA)
    original = service._server.url_for(ref)
    monkeypatch.setattr(service._scaler, "scaled", lambda *_args: (_ for _ in ()).throw(OptimizeError("no_encoder")))
    for bucket in BUCKETS:
        service._serve_path(f"sized:{bucket}:{ref}")
    assert set(_listed(service.theme_images())[ref].values()) == {original}


def test_a_scale_failure_expires_and_a_later_success_clears_it(service, monkeypatch, tmp_path):
    ref = _ids(service)["huge.jpg"]
    urls = service.register_theme_image(ref, VIDA)["urls"]
    monkeypatch.setattr(service._scaler, "scaled", lambda *_args: (_ for _ in ()).throw(OptimizeError("encode_failed")))
    _get(urls["1920"])
    assert _listed(service.theme_images())[ref]["1920"] == urls["2560"]
    for key in service._scale_failures:
        service._scale_failures[key] -= ambient_service._SCALE_FAILURE_TTL_SEC
    assert _listed(service.theme_images())[ref]["1920"] == urls["1920"], "an old failure is tried again"
    _get(urls["1920"])
    copy = _touch(tmp_path / "copy.jpg", b"SCALED")
    for key in service._scale_failures:
        service._scale_failures[key] -= ambient_service._SCALE_FAILURE_TTL_SEC
    monkeypatch.setattr(service._scaler, "scaled", lambda *_args: str(copy))
    assert _get(urls["1920"])[0] == b"SCALED"
    assert not service._scale_failures


def test_remembered_failures_are_bounded(service):
    for index in range(ambient_service._MAX_SCALE_FAILURES + 40):
        service._record_scale((f"/p{index}.jpg", 1, 0), 1280, ok=False)
    assert len(service._scale_failures) == ambient_service._MAX_SCALE_FAILURES
    assert service._scale_failed(("/p0.jpg", 1, 0), 1280) is False
    assert service._scale_failed((f"/p{ambient_service._MAX_SCALE_FAILURES + 39}.jpg", 1, 0), 1280) is True


def test_listing_probes_each_file_version_once(service, home, monkeypatch):
    ref = _ids(service)["huge.jpg"]
    service.register_theme_image(ref, VIDA)
    probes = []
    real = ambient_service.probe_image
    monkeypatch.setattr(ambient_service, "probe_image", lambda path: probes.append(path) or real(path))
    service._image_probes.clear()
    for _ in range(3):
        assert ref in _listed(service.theme_images())
    assert len(probes) == 1
    photo = home / "Pictures" / "huge.jpg"
    stat = photo.stat()
    os.utime(photo, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    _listed(service.theme_images())
    assert len(probes) == 2


def test_a_symlink_swapped_in_for_a_photo_is_not_served(service, home, tmp_path):
    ref = _ids(service)["dunes.jpg"]
    service.register_theme_image(ref, VIDA)
    service._index.clear()
    outside = _touch(tmp_path / "outside" / "secret.jpg", jpeg_header(10, 10))
    photo = home / "Pictures" / "dunes.jpg"
    photo.unlink()
    os.symlink(outside, photo)
    assert _listed(service.theme_images()) == {}


def test_the_store_is_bounded_and_ignores_corrupt_entries(tmp_path):
    path = tmp_path / "theme-images.json"
    good = str(tmp_path / "a.jpg")
    path.write_text(json.dumps({"version": 1, "images": {
        media_id(good): {"path": good, "at": 5},
        "local:forged": {"path": good, "at": 9},
        media_id("relative.jpg"): {"path": "relative.jpg", "at": 1},
    }}))
    store = ThemeImageStore(str(path), limit=2)
    assert store.refs() == [media_id(good)]
    for index in range(3):
        photo = str(tmp_path / f"p{index}.jpg")
        store.remember(media_id(photo), photo, VIDA, now=10 + index)
    assert sorted(store.refs()) == sorted([media_id(str(tmp_path / "p1.jpg")), media_id(str(tmp_path / "p2.jpg"))])
    assert sorted(ThemeImageStore(str(path), limit=2).refs()) == sorted(store.refs())
    with pytest.raises(ValueError):
        store.remember("local:forged", good, VIDA)


def test_a_corrupt_store_starts_empty(tmp_path):
    path = tmp_path / "theme-images.json"
    path.write_text("{nope")
    assert ThemeImageStore(str(path)).refs() == []


# Sizes and scaling


@pytest.mark.parametrize(("max_side", "bucket"), [
    (800, 1280), (1280, 1280), (1281, 1920), (1920, 1920), (2400, 2560), (3840, 2560),
    (None, 2560), (0, 2560), (-5, 2560), (float("nan"), 2560), (float("inf"), 2560), (True, 2560), ("1920", 2560),
])
def test_screen_sizes_snap_up_to_a_bucket_never_above_1440p(max_side, bucket):
    assert bucket_for(max_side) == bucket


def test_probe_reads_jpeg_size_and_orientation_without_decoding(tmp_path):
    assert probe(str(_touch(tmp_path / "a.jpg", jpeg_header(4000, 3000, orientation=6)))) == ImageInfo(4000, 3000, 6, False)
    assert probe(str(_touch(tmp_path / "b.jpg", b"\xff\xd8garbage"))) is None
    assert probe(str(_touch(tmp_path / "c.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 4))) is None
    assert probe(str(tmp_path / "missing.jpg")) is None


def test_probe_walks_past_large_jpeg_segments_to_the_frame_header(tmp_path):
    filler = b"\xff\xe2" + struct.pack(">H", 65535) + b"\x00" * 65533
    header = jpeg_header(5000, 4000, orientation=8)
    data = header[:2] + _exif(8) + filler * 5 + header[2 + len(_exif(8)):]
    assert data.index(b"\xff\xc0") > 256 * 1024
    assert probe(str(_touch(tmp_path / "big-exif.jpg", data))) == ImageInfo(5000, 4000, 8, False)
    assert probe(str(_touch(tmp_path / "cut.jpg", data[:300 * 1024]))) is None


def _box(kind, payload):
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def _ispe(width, height):
    return _box(b"ispe", b"\x00\x00\x00\x00" + struct.pack(">II", width, height))


def avif_header(properties, associations=None, primary=1):
    """An AVIF that is only a header: `associations` maps item ids to 1-based property indices."""
    ipco = _box(b"ipco", b"".join(properties))
    boxes = [_box(b"pitm", b"\x00\x00\x00\x00" + struct.pack(">H", primary)), ]
    iprp = ipco
    if associations is not None:
        entries = b"".join(struct.pack(">HB", item, len(indices)) + bytes(indices) for item, indices in associations.items())
        iprp += _box(b"ipma", b"\x00\x00\x00\x00" + struct.pack(">I", len(associations)) + entries)
    boxes.append(_box(b"iprp", iprp))
    meta = _box(b"meta", b"\x00\x00\x00\x00" + b"".join(boxes))
    return _box(b"ftyp", b"avif\x00\x00\x00\x00mif1") + meta + _box(b"mdat", b"\x00" * 16)


def test_probe_reads_a_grid_avif_by_its_primary_item_not_a_tile(tmp_path):
    grid = avif_header([_ispe(512, 512), _ispe(8192, 6144)], {1: [2], 2: [1], 3: [1]})
    assert probe(str(_touch(tmp_path / "grid.avif", grid))) == ImageInfo(8192, 6144, 1, True)
    tiles_first = avif_header([_ispe(8192, 6144), _ispe(512, 512)], {2: [1], 1: [2]}, primary=1)
    assert probe(str(_touch(tmp_path / "primary.avif", tiles_first))) == ImageInfo(512, 512, 1, True)
    unmapped = avif_header([_ispe(512, 512), _ispe(20000, 10000)])
    assert probe(str(_touch(tmp_path / "unmapped.avif", unmapped))) == ImageInfo(20000, 10000, 1, True)


def test_orientation_and_alpha_shape_the_command():
    rotated = scale_command("ffmpeg", "in.jpg", "out.jpg", ImageInfo(4000, 3000, 6), 1920)
    assert "-noautorotate" in rotated
    assert rotated[rotated.index("-vf") + 1].startswith("transpose=1,scale=w=1920:h=1920:force_original_aspect_ratio=decrease")
    assert "mjpeg" in rotated and "-map_metadata" in rotated
    transparent = scale_command("ffmpeg", "in.png", "out.png", ImageInfo(4000, 3000, 1, True), 2560)
    assert transparent[transparent.index("-c:v") + 1] == "png"


def _fake_scaler(tmp_path):
    runs = []

    def run(command, _cancel, timeout):
        runs.append((command, timeout))
        with open(command[-1], "wb") as handle:
            handle.write(b"SCALED")
        return 0

    return ImageScaler(str(tmp_path / "scaled"), find=lambda: "ffmpeg", run=run), runs


def test_a_copy_is_made_once_per_size_and_remade_when_the_photo_changes(tmp_path):
    scaler, runs = _fake_scaler(tmp_path)
    photo = _touch(tmp_path / "p.jpg", jpeg_header(4000, 3000))
    info = probe(str(photo))
    first = scaler.scaled("local:p", str(photo), info, 1920)
    assert scaler.scaled("local:p", str(photo), info, 1920) == first
    assert len(runs) == 1 and runs[0][1] == image_scaler.SCALE_TIMEOUT_SEC
    assert scaler.scaled("local:p", str(photo), info, 1280) != first
    stat = photo.stat()
    os.utime(photo, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert scaler.scaled("local:p", str(photo), info, 1920) != first
    assert len(runs) == 3


def test_the_copy_cache_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(image_scaler, "CACHE_MAX_FILES", 2)
    scaler, _ = _fake_scaler(tmp_path)
    made = []
    for index in range(4):
        photo = _touch(tmp_path / f"p{index}.jpg", jpeg_header(4000, 3000))
        made.append(scaler.scaled(f"local:{index}", str(photo), probe(str(photo)), 1280))
        os.utime(made[-1], (index, index))
    assert sorted(os.listdir(tmp_path / "scaled")) == sorted(os.path.basename(path) for path in made[-2:])


def test_a_copy_served_a_moment_ago_is_not_pruned(tmp_path, monkeypatch):
    monkeypatch.setattr(image_scaler, "CACHE_MAX_FILES", 1)
    scaler, runs = _fake_scaler(tmp_path)
    first_photo = _touch(tmp_path / "a.jpg", jpeg_header(4000, 3000))
    second_photo = _touch(tmp_path / "b.jpg", jpeg_header(4000, 3000))
    first = scaler.scaled("local:a", str(first_photo), probe(str(first_photo)), 1280)
    scaler.scaled("local:b", str(second_photo), probe(str(second_photo)), 1280)
    assert os.path.isfile(first), "a request may be sending it right now"
    os.utime(first, (1, 1))
    third_photo = _touch(tmp_path / "c.jpg", jpeg_header(4000, 3000))
    scaler.scaled("local:c", str(third_photo), probe(str(third_photo)), 1280)
    assert not os.path.exists(first)
    assert len(runs) == 3


def test_a_copy_pruned_after_the_check_is_made_again_and_a_vanished_source_is_none(tmp_path):
    scaler, runs = _fake_scaler(tmp_path)
    photo = _touch(tmp_path / "p.jpg", jpeg_header(4000, 3000))
    info = probe(str(photo))
    copy = scaler.scaled("local:p", str(photo), info, 1280)
    os.unlink(copy)
    assert scaler.scaled("local:p", str(photo), info, 1280) == copy
    assert os.path.isfile(copy) and len(runs) == 2
    photo.unlink()
    assert image_scaler.output_name("local:p", str(photo), info, 1280) is None
    assert scaler.scaled("local:p", str(photo), info, 1280) is None


def test_scaling_refuses_absurd_pictures_and_reports_a_missing_encoder(tmp_path):
    scaler = ImageScaler(str(tmp_path / "scaled"), find=lambda: None)
    photo = _touch(tmp_path / "p.jpg", jpeg_header(4000, 3000))
    with pytest.raises(OptimizeError, match="too_large"):
        scaler.scaled("local:p", str(photo), ImageInfo(20000, 10000), 1280)
    with pytest.raises(OptimizeError, match="no_encoder"):
        scaler.scaled("local:p", str(photo), probe(str(photo)), 1280)


def _render(path, source):
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-f", "lavfi", "-i", source, "-frames:v", "1", str(path)], check=True)
    return path


def _size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return tuple(int(value) for value in out.stdout.strip().split(","))


def _corner(path):
    raw = subprocess.run([FFMPEG, "-loglevel", "error", "-noautorotate", "-i", str(path), "-vf", "crop=8:8:0:0,scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return tuple(raw[:3])


@needs_ffmpeg
def test_exif_rotation_is_applied_once_like_ffmpeg_itself_would(tmp_path):
    base = _render(tmp_path / "base.jpg", "testsrc2=s=3200x1600")
    data = base.read_bytes()
    rotated = _touch(tmp_path / "rotated.jpg", data[:2] + _exif(6) + data[2:])
    reference = tmp_path / "reference.png"
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", str(rotated), "-frames:v", "1", str(reference)], check=True)
    out = ImageScaler(str(tmp_path / "scaled")).scaled("local:r", str(rotated), probe(str(rotated)), 1920)
    assert _size(out) == (960, 1920)
    assert all(abs(a - b) < 40 for a, b in zip(_corner(out), _corner(reference)))


@needs_ffmpeg
def test_real_scaling_keeps_aspect_and_alpha(tmp_path):
    photo = _render(tmp_path / "wide.png", "color=blue@0.5:s=3000x1000,format=rgba")
    out = ImageScaler(str(tmp_path / "scaled")).scaled("local:p", str(photo), probe(str(photo)), 1280)
    assert out.endswith(".png") and _size(out) == (1280, 427)


@needs_ffmpeg
def test_a_corrupt_body_behind_a_valid_header_fails_cleanly(tmp_path):
    photo = _touch(tmp_path / "bad.jpg", jpeg_header(4000, 3000) + b"\x00" * 64)
    with pytest.raises(OptimizeError, match="encode_failed"):
        ImageScaler(str(tmp_path / "scaled")).scaled("local:p", str(photo), probe(str(photo)), 1280)
    assert [name for name in os.listdir(tmp_path / "scaled") if ".part." in name] == []


@needs_ffmpeg
def test_the_server_scales_on_first_request_and_serves_the_cached_copy(service, home, tmp_path):
    photo = _render(home / "Pictures" / "real.jpg", "testsrc2=s=4000x3000")
    ref = _ids(service)["real.jpg"]
    urls = service.register_theme_image(ref, VIDA)["urls"]
    body, headers = _get(urls["1920"])
    assert headers["Content-Type"] == "image/jpeg"
    assert headers["Access-Control-Allow-Origin"] == STEAM_UI_ORIGIN
    copy = _touch(tmp_path / "served.jpg", body)
    assert _size(copy) == (1920, 1440)
    assert _get(urls["1920"])[0] == body
    assert photo.stat().st_size != len(body)


# Warming at pick time


def test_picking_warms_the_copy_for_the_screen_without_waiting_for_it(tmp_path, home):
    gate = threading.Event()
    runner = BlockingRunner(gate)
    svc = _warming_service(tmp_path, home, runner)
    try:
        ref = _ids(svc)["huge.jpg"]
        started = time.monotonic()
        picked = svc.register_theme_image(ref, VIDA, 1280)
        assert time.monotonic() - started < 1
        assert "sized%3A1280%3A" in picked["urls"]["1280"]
        assert runner.started.wait(5)
        gate.set()
        deadline = time.monotonic() + 5
        while not os.listdir(tmp_path / "cache" / "theme-images") or any(".part." in n for n in os.listdir(tmp_path / "cache" / "theme-images")):
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert _get(picked["urls"]["1280"])[0] == b"SCALED"
        assert len(runner.runs) == 1, "the request found the warmed copy"
    finally:
        svc.close()


def test_a_photo_that_fits_is_not_warmed(tmp_path, home):
    runner = BlockingRunner()
    svc = _warming_service(tmp_path, home, runner)
    try:
        svc.register_theme_image(_ids(svc)["dunes.jpg"], VIDA, 2560)
        assert svc._warm_theme_image(_ids(svc)["dunes.jpg"], probe(str(home / "Pictures" / "dunes.jpg")), 2560) is None
        assert runner.runs == []
    finally:
        svc.close()


def test_a_failed_warm_is_only_logged(tmp_path, home):
    svc = _warming_service(tmp_path, home, BlockingRunner(code=1))
    try:
        ref = _ids(svc)["huge.jpg"]
        assert "ref" in svc.register_theme_image(ref, VIDA, 1280)
        svc._warm_theme_image(ref, probe(str(home / "Pictures" / "huge.jpg")), 1920).join(5)
        details = [e["detail"] for e in svc.diagnostics()["events"]]
        assert "scale:encode_failed" in details
        listed = _listed(svc.theme_images())[ref]
        assert listed["1920"] == listed["2560"], "the failed size points at the next larger one"
    finally:
        svc.close()


# The scaler lock


def test_a_cached_copy_is_served_while_another_picture_encodes(tmp_path):
    gate = threading.Event()
    runner = BlockingRunner()
    scaler = ImageScaler(str(tmp_path / "scaled"), find=lambda: "ffmpeg", run=runner)
    ready = _touch(tmp_path / "ready.jpg", jpeg_header(4000, 3000))
    slow = _touch(tmp_path / "slow.jpg", jpeg_header(4000, 3000))
    cached = scaler.scaled("local:ready", str(ready), probe(str(ready)), 1280)
    runner.gate = gate
    runner.started.clear()
    encoding = threading.Thread(target=scaler.scaled, args=("local:slow", str(slow), probe(str(slow)), 1280))
    encoding.start()
    assert runner.started.wait(5)
    hit = []
    reader = threading.Thread(target=lambda: hit.append(scaler.scaled("local:ready", str(ready), probe(str(ready)), 1280)))
    reader.start()
    reader.join(1)
    assert hit == [cached], "the cache hit did not wait for the other encode"
    gate.set()
    encoding.join(5)


def test_two_requests_for_the_same_missing_copy_encode_once(tmp_path):
    gate = threading.Event()
    runner = BlockingRunner(gate)
    scaler = ImageScaler(str(tmp_path / "scaled"), find=lambda: "ffmpeg", run=runner)
    photo = _touch(tmp_path / "p.jpg", jpeg_header(4000, 3000))
    results = []
    threads = [threading.Thread(target=lambda: results.append(scaler.scaled("local:p", str(photo), probe(str(photo)), 1920))) for _ in range(2)]
    for thread in threads:
        thread.start()
    assert runner.started.wait(5)
    gate.set()
    for thread in threads:
        thread.join(5)
    assert len(runner.runs) == 1 and len(set(results)) == 1


# keepImages


def _copies(tmp_path):
    folder = tmp_path / "cache" / "theme-images"
    return sorted(os.listdir(folder)) if folder.exists() else []


def _keeping_service(tmp_path, home):
    svc = _warming_service(tmp_path, home, BlockingRunner())
    svc._warm_theme_image = lambda *_args: None
    return svc


def test_a_theme_forgets_only_its_own_pictures_and_their_copies(tmp_path, home):
    svc = _keeping_service(tmp_path, home)
    try:
        ids = _ids(svc)
        svc.register_theme_image(ids["dunes.jpg"], VIDA)
        svc.register_theme_image(ids["huge.jpg"], VIDA)
        other = svc.register_theme_image(ids["huge.jpg"], DUO)
        _get(other["urls"]["1280"])
        _get(other["urls"]["1920"])
        assert len(_copies(tmp_path)) == 2
        assert svc.keep_theme_images(VIDA, []) == [ids["dunes.jpg"]]
        assert set(_listed(svc.theme_images())) == {ids["huge.jpg"]}, "Duo still keeps the big photo"
        assert len(_copies(tmp_path)) == 2
        assert svc.keep_theme_images(DUO, []) == [ids["huge.jpg"]]
        assert _listed(svc.theme_images()) == {}
        assert _copies(tmp_path) == []
        assert (home / "Pictures" / "huge.jpg").read_bytes() == jpeg_header(4000, 3000)
        assert (home / "Pictures" / "dunes.jpg").exists()
        reopened = _service(tmp_path, home)
        assert _listed(reopened.theme_images()) == {}
        reopened.close()
    finally:
        svc.close()


def test_a_theme_cannot_drop_another_themes_picture(tmp_path, home):
    svc = _keeping_service(tmp_path, home)
    try:
        ref = _ids(svc)["dunes.jpg"]
        svc.register_theme_image(ref, DUO)
        assert svc.keep_theme_images(VIDA, []) == []
        assert list(_listed(svc.theme_images())) == [ref]
    finally:
        svc.close()


def test_a_kept_ref_the_store_lost_is_adopted_again_while_the_library_has_it(tmp_path, home):
    svc = _keeping_service(tmp_path, home)
    try:
        ids = _ids(svc)
        svc.register_theme_image(ids["dunes.jpg"], VIDA)
        assert svc.keep_theme_images(VIDA, []) == [ids["dunes.jpg"]]
        assert svc.keep_theme_images(VIDA, [ids["dunes.jpg"]]) == []
        assert list(_listed(svc.theme_images())) == [ids["dunes.jpg"]]
        assert svc._theme_images.owners(ids["dunes.jpg"]) == [VIDA]
        assert svc.keep_theme_images(VIDA, [ids["loop.webm"], "local:0000"]) == [ids["dunes.jpg"]]
        assert _listed(svc.theme_images()) == {}
    finally:
        svc.close()


def test_keeping_another_themes_picture_does_not_take_it_over(tmp_path, home):
    svc = _keeping_service(tmp_path, home)
    try:
        ref = _ids(svc)["dunes.jpg"]
        svc.register_theme_image(ref, DUO)
        assert svc.keep_theme_images(VIDA, [ref]) == []
        assert svc._theme_images.owners(ref) == [DUO]
        assert svc.keep_theme_images(DUO, []) == [ref]
    finally:
        svc.close()


def test_an_unchanged_set_writes_nothing_and_walks_no_cache(tmp_path, home, monkeypatch):
    svc = _keeping_service(tmp_path, home)
    try:
        ids = _ids(svc)
        svc.register_theme_image(ids["dunes.jpg"], VIDA)
        svc.keep_theme_images(VIDA, [ids["dunes.jpg"]])
        writes, forgets = [], []
        monkeypatch.setattr(theme_images, "atomic_json_save", lambda *args: writes.append(args))
        monkeypatch.setattr(svc._scaler, "forget", lambda ref: forgets.append(ref))
        for _ in range(3):
            assert svc.keep_theme_images(VIDA, [ids["dunes.jpg"]]) == []
        assert writes == [] and forgets == []
    finally:
        svc.close()


@pytest.mark.parametrize("refs", ["local:a", None, [1], ["x" * 513], ["local:a"] * 513, [""]])
def test_invalid_keep_input_is_ignored(service, refs):
    ref = _ids(service)["dunes.jpg"]
    service.register_theme_image(ref, VIDA)
    assert service.keep_theme_images(VIDA, refs) == []
    assert service.keep_theme_images("", []) == []
    assert list(_listed(service.theme_images())) == [ref]


def test_pictures_saved_before_owners_are_adopted_never_dropped_by_omission(tmp_path):
    path = tmp_path / "theme-images.json"
    photo = str(tmp_path / "old.jpg")
    path.write_text(json.dumps({"version": 1, "images": {media_id(photo): {"path": photo, "at": 1}}}))
    store = ThemeImageStore(str(path))
    assert store.owners(media_id(photo)) == []
    assert store.keep(VIDA, set()) == []
    assert store.refs() == [media_id(photo)]
    assert store.keep(VIDA, {media_id(photo)}) == []
    assert store.owners(media_id(photo)) == [VIDA]
    assert store.keep(VIDA, set()) == [media_id(photo)]


class Host(AmbientRpc):
    def __init__(self, tmp_path):
        self._tmp = tmp_path
        _touch(tmp_path / "home" / "Pictures" / "a.jpg", jpeg_header(800, 600))

    def _ambient_service_factory(self):
        return AmbientService(str(self._tmp / "state"), str(self._tmp / "cache"), str(self._tmp / "home"))


def test_rpc_registers_and_lists_theme_images(tmp_path):
    host = Host(tmp_path)
    try:
        assert asyncio.run(host.register_ambient_theme_image(None, VIDA)) == {"error": "unknown_media"}
        assert asyncio.run(host.register_ambient_theme_image("x" * 513, VIDA)) == {"error": "unknown_media"}
        ref = asyncio.run(host.scan_ambient_sources())["collections"]["known.images"][0]["id"]
        picked = asyncio.run(host.register_ambient_theme_image(ref, VIDA))
        assert _listed(asyncio.run(host.get_ambient_theme_images())) == {ref: picked["urls"]}
        assert set(picked["urls"]) == {str(bucket) for bucket in BUCKETS}
        assert asyncio.run(host.keep_ambient_theme_images(None, [])) == []
        assert asyncio.run(host.keep_ambient_theme_images(VIDA, [])) == [ref]
    finally:
        host._ambient_stop()
