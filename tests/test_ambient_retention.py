import errno
import json
from pathlib import Path

import pytest

from ambient.adapters.library_scan import media_id
from ambient.adapters.optimizer import Optimized, output_name
from ambient.core.collections import stable_id
from ambient.service import AmbientService


@pytest.fixture
def svc(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    service = AmbientService(str(tmp_path / "state"), str(tmp_path / "cache"), str(home))

    def convert(source, cache_dir, height, cancel=None, fps=30):
        target = Path(cache_dir) / output_name(source, height, fps)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"converted")
        return Optimized(str(target), "test")

    monkeypatch.setattr("ambient.service.optimize", convert)
    yield service
    service.close()


def source(svc, tmp_path):
    folder = tmp_path / "home" / "Backgrounds"
    folder.mkdir()
    original = folder / "original.mp4"
    original.write_bytes(b"original")
    svc.add_folder(str(folder))
    svc.scan()
    ref = media_id(str(original))
    svc.optimize_media(ref, 200)
    target = tmp_path / "cache" / "optimized" / output_name(str(original), 200)
    return folder, original, ref, target


def test_removing_last_folder_removes_only_generated_copy(svc, tmp_path):
    folder, original, _, target = source(svc, tmp_path)
    unknown = target.parent / ("opt-" + "f" * 32 + ".mp4")
    unknown.write_bytes(b"legacy")
    svc.remove_item("background", stable_id("folder", str(folder)))
    assert not target.exists()
    assert original.read_bytes() == b"original"
    assert unknown.read_bytes() == b"legacy"


def test_shared_folder_and_game_references_keep_copy(svc, tmp_path):
    folder, original, ref, target = source(svc, tmp_path)
    svc.add_folder(str(folder.parent))
    svc.remove_item("background", stable_id("folder", str(folder)))
    assert target.exists()
    settings = svc.get_state()["settings"]
    settings["background"]["perGame"] = {"10": ref, "20": ref}
    svc.save_settings(settings)
    svc.remove_item("background", stable_id("folder", str(folder.parent)))
    assert target.exists()
    settings = svc.get_state()["settings"]
    settings["background"]["perGame"].pop("10")
    svc.save_settings(settings)
    assert target.exists()
    settings["background"]["perGame"].clear()
    svc.save_settings(settings)
    assert not target.exists()
    assert original.read_bytes() == b"original"


def test_removal_while_conversion_runs_does_not_leave_orphan(svc, tmp_path, monkeypatch):
    folder, original, ref, target = source(svc, tmp_path)
    convert = __import__("ambient.service", fromlist=["optimize"]).optimize

    def removing(source, cache, height, cancel=None, fps=30):
        svc.remove_item("background", stable_id("folder", str(folder)))
        return convert(source, cache, height, cancel, fps)

    monkeypatch.setattr("ambient.service.optimize", removing)
    result = svc.optimize_media(ref, 200)
    assert result == {"error": "unused_media"}
    assert not target.exists()
    assert original.read_bytes() == b"original"


def test_retention_survives_service_reload(svc, tmp_path):
    folder, original, _, target = source(svc, tmp_path)
    other = AmbientService(str(tmp_path / "state"), str(tmp_path / "cache"), str(tmp_path / "home"))
    try:
        other.remove_item("background", stable_id("folder", str(folder)))
        assert not target.exists()
        assert original.exists()
    finally:
        other.close()


def test_downloads_over_one_gib_are_kept(svc, tmp_path, monkeypatch):
    from ambient.core.cache_policy import cache_filename

    def download(url, directory):
        target = Path(directory) / cache_filename(url, "video/mp4")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as stream:
            stream.truncate(600 * 1024 * 1024)
        return str(target)

    monkeypatch.setattr("ambient.service.download", download)
    for suffix in ("a", "b"):
        url = f"https://example.test/{suffix}.mp4"
        svc.add_favorite("background", url, suffix)
        svc.cache_remote(url)
    assert len(list((tmp_path / "cache").glob("*.mp4"))) == 2


def test_confirmed_uninstall_prunes_only_exclusive_game_copy(svc, tmp_path, monkeypatch):
    folder, original, ref, target = source(svc, tmp_path)
    current = {"installed": ["10", "20"], "libraries": {}, "complete": True}
    monkeypatch.setattr("ambient.service.installed_snapshot", lambda *args: current)
    svc.reconcile_games()
    settings = svc.get_state()["settings"]
    settings["background"]["perGame"] = {"10": ref, "20": ref}
    svc.save_settings(settings)
    svc.remove_item("background", stable_id("folder", str(folder)))
    current = {"installed": ["20"], "libraries": {}, "complete": False}
    assert not svc.reconcile_games()
    assert "10" in svc.get_state()["settings"]["background"]["perGame"]
    current = {**current, "complete": True}
    assert svc.reconcile_games()
    assert target.exists()
    current = {**current, "installed": []}
    assert svc.reconcile_games()
    assert not target.exists()
    assert original.read_bytes() == b"original"


def test_registry_cannot_delete_an_original(svc, tmp_path):
    _, original, _, _ = source(svc, tmp_path)
    registry = tmp_path / "cache" / "generated.json"
    records = json.loads(registry.read_text())
    records["../home/Backgrounds/original.mp4"] = {"ref": "local:fake", "source": "", "collections": [], "managed": True}
    registry.write_text(json.dumps(records))
    other = AmbientService(str(tmp_path / "state"), str(tmp_path / "cache"), str(tmp_path / "home"))
    try:
        other.save_settings({})
        assert original.read_bytes() == b"original"
    finally:
        other.close()


def test_remote_favorite_removal_preserves_shared_game_reference(svc, tmp_path, monkeypatch):
    from ambient.core.cache_policy import cache_filename

    url = "https://example.test/background.mp4"
    def download(url, directory):
        target = Path(directory) / cache_filename(url, "video/mp4")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"download")
        return str(target)

    monkeypatch.setattr("ambient.service.download", download)
    svc.add_favorite("background", url, "Video")
    svc.cache_remote(url)
    target = tmp_path / "cache" / cache_filename(url, "video/mp4")
    settings = svc.get_state()["settings"]
    settings["background"]["perGame"] = {"10": "remote:" + url}
    svc.save_settings(settings)
    svc.remove_item("background", stable_id("fav", url))
    assert target.exists()
    settings = svc.get_state()["settings"]
    settings["background"]["perGame"].clear()
    svc.save_settings(settings)
    assert not target.exists()


def test_generated_cache_symlink_cannot_delete_original(svc, tmp_path):
    folder, original, _, target = source(svc, tmp_path)
    target.unlink()
    target.symlink_to(original)
    svc.remove_item("background", stable_id("folder", str(folder)))
    assert original.read_bytes() == b"original"
    assert target.is_symlink()


def test_first_inventory_does_not_infer_prior_uninstall(svc, monkeypatch):
    settings = svc.get_state()["settings"]
    settings["background"]["perGame"] = {"10": "local:existing"}
    svc.save_settings(settings)
    monkeypatch.setattr("ambient.service.installed_snapshot", lambda *args: {"installed": [], "libraries": {}, "complete": True})
    assert not svc.reconcile_games()
    assert svc.get_state()["settings"]["background"]["perGame"] == {"10": "local:existing"}


def test_queued_conversion_does_not_create_copy_after_last_consumer_is_removed(svc, tmp_path):
    folder, original, ref, target = source(svc, tmp_path)
    svc.remove_item("background", stable_id("folder", str(folder)))
    assert svc.optimize_media(ref, 200) == {"error": "unused_media"}
    assert not target.exists()
    assert original.read_bytes() == b"original"


@pytest.mark.parametrize("failure", [errno.ENOSPC, errno.EDQUOT])
def test_registry_storage_error_removes_only_new_conversion(svc, tmp_path, monkeypatch, failure):
    _, original, ref, existing = source(svc, tmp_path)
    target = existing.parent / output_name(str(original), 400)
    registry = tmp_path / "cache" / "generated.json"
    before = registry.read_bytes()

    def full(*args):
        raise OSError(failure, "full")

    monkeypatch.setattr("ambient.adapters.generated_cache.atomic_json_save", full)
    assert svc.optimize_media(ref, 400) == {"error": "no_space"}
    assert not target.exists()
    assert existing.read_bytes() == b"converted"
    assert original.read_bytes() == b"original"
    assert registry.read_bytes() == before


@pytest.mark.parametrize("failure", [errno.ENOSPC, errno.EDQUOT])
def test_registry_storage_error_preserves_preexisting_unregistered_conversion(svc, tmp_path, monkeypatch, failure):
    from ambient.adapters import optimizer

    _, original, ref, existing = source(svc, tmp_path)
    cached = existing.parent / output_name(str(original), 400)
    cached.write_bytes(b"PREEXISTING")

    def full(*args):
        raise OSError(failure, "full")

    monkeypatch.setattr("ambient.adapters.generated_cache.atomic_json_save", full)
    monkeypatch.setattr("ambient.service.optimize", optimizer.optimize)
    monkeypatch.setattr(optimizer, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    assert svc.optimize_media(ref, 400) == {"error": "no_space"}
    assert cached.read_bytes() == b"PREEXISTING"
    assert existing.read_bytes() == b"converted"
    assert original.read_bytes() == b"original"


def test_queued_remote_download_stops_after_its_collection_is_removed(svc, tmp_path, monkeypatch):
    def unexpected_download(*args):
        pytest.fail("removed collection must not start a download")

    monkeypatch.setattr("ambient.service.download", unexpected_download)
    svc.remove_item("background", "suggested.nasa")
    result = svc.cache_remote("https://example.test/background.jpg", "suggested.nasa")
    assert result == {"error": "unused_media"}
    assert not list((tmp_path / "cache").glob("*.jpg"))


@pytest.mark.parametrize("preexisting", [False, True])
def test_remote_registry_storage_error_removes_only_new_download(svc, tmp_path, monkeypatch, preexisting):
    from ambient.core.cache_policy import cache_filename

    url = "https://example.test/background.jpg"
    target = tmp_path / "cache" / cache_filename(url, "image/jpeg")
    svc.add_favorite("background", url, "Background")

    def download(url, directory):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"DOWNLOADED")
        return str(target)

    def full(*args):
        raise OSError(errno.ENOSPC, "full")

    monkeypatch.setattr("ambient.service.download", download)
    if preexisting:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PREEXISTING")
        svc._remember_url(url, target.name)
    monkeypatch.setattr("ambient.adapters.generated_cache.atomic_json_save", full)
    assert svc.cache_remote(url) == {"error": "no_space"}
    if preexisting:
        assert target.read_bytes() == b"PREEXISTING"
    else:
        assert not target.exists()
