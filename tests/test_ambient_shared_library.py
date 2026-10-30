from pathlib import Path
import errno
import urllib.request

import pytest

from ambient.adapters.library_scan import media_id
from ambient.adapters.optimizer import Optimized, output_name
from ambient.core.collections import stable_id
from ambient.service import AmbientService


@pytest.fixture
def service(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    svc = AmbientService(str(tmp_path / "state"), str(tmp_path / "cache"), str(home))
    monkeypatch.setattr(svc, "media_url", lambda media: "http://127.0.0.1/media/" + media)

    def convert(source, cache_dir, height, cancel=None, fps=30):
        target = Path(cache_dir) / output_name(source, height, fps)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"converted")
        return Optimized(str(target), "test")

    monkeypatch.setattr("ambient.service.optimize", convert)
    yield svc
    svc.close()


def mixed_folder(tmp_path, name="Mixed"):
    folder = tmp_path / "home" / name
    folder.mkdir()
    for filename in ("photo.jpg", "movie.mp4", "song.mp3"):
        (folder / filename).write_bytes(b"original")
    return folder


def test_shared_folder_has_all_media_with_compatible_filtered_views(service, tmp_path):
    folder = mixed_folder(tmp_path)
    saved = service.add_folder(str(folder), "library")
    assert saved["collections"]["folders"] == [str(folder)]
    assert saved["music"]["folders"] == []
    scanned = service.scan()
    key = stable_id("folder", str(folder))
    assert {item["kind"] for item in scanned["library"][key]} == {"image", "video", "audio"}
    assert {item["kind"] for item in scanned["collections"][key]} == {"image", "video"}
    assert [item["name"] for item in scanned["music"]] == ["song.mp3"]
    assert all("path" not in item for item in scanned["library"][key])


def test_legacy_sources_are_unified_without_rewriting_settings_after_restart(service, tmp_path):
    first, second = mixed_folder(tmp_path, "First"), mixed_folder(tmp_path, "Second")
    saved = service.add_folder(str(first), "background")
    saved = service.add_folder(str(first), "music")
    saved = service.add_folder(str(second), "music")
    reopened = AmbientService(str(tmp_path / "state"), str(tmp_path / "cache"), str(tmp_path / "home"))
    try:
        state = reopened.get_state()
        assert state["settings"] == saved
        assert state["settings"]["version"] == 1
        assert [entry["path"] for entry in state["collections"] if entry["kind"] == "folder"] == [str(first), str(second)]
        audio = reopened.scan()["music"]
        assert len(audio) == 2 and len({item["id"] for item in audio}) == 2
    finally:
        reopened.close()


def test_shared_folder_removal_clears_both_legacy_lists_and_selection(service, tmp_path):
    folder = mixed_folder(tmp_path)
    service.add_folder(str(folder), "background")
    settings = service.add_folder(str(folder), "music")
    key = stable_id("folder", str(folder))
    settings["background"]["collections"] = [key]
    service.save_settings(settings)
    removed = service.remove_item("library", key)
    assert removed["collections"]["folders"] == []
    assert removed["music"]["folders"] == []
    assert removed["background"]["collections"] == []
    assert key not in service.scan()["library"]
    assert (folder / "movie.mp4").read_bytes() == b"original"


def test_known_music_exposes_mixed_media_and_preserves_generated_ownership(service, tmp_path):
    folder = mixed_folder(tmp_path, "Music")
    assert "known.music" in {entry["id"] for entry in service.get_state()["collections"]}
    assert {item["kind"] for item in service.scan()["library"]["known.music"]} == {"image", "video", "audio"}
    result = service.optimize_media(media_id(str(folder / "movie.mp4")), 200)
    assert "id" in result
    service.save_settings({"version": 1})
    assert list((tmp_path / "cache/optimized").glob("*.mp4"))


def test_music_folder_copy_is_kept_until_all_owners_are_removed(service, tmp_path):
    folder = mixed_folder(tmp_path)
    service.add_folder(str(folder), "music")
    service.scan()
    ref = media_id(str(folder / "movie.mp4"))
    assert "id" in service.optimize_media(ref, 200)
    target = tmp_path / "cache/optimized" / output_name(str(folder / "movie.mp4"), 200)
    settings = service.get_state()["settings"]
    settings["background"]["perGame"] = {"10": ref}
    service.save_settings(settings)
    service.remove_item("library", stable_id("folder", str(folder)))
    assert target.exists()
    service.save_settings({"version": 1})
    assert not target.exists()
    assert (folder / "movie.mp4").exists()


def test_reset_music_only_sources_prunes_their_generated_copies(service, tmp_path):
    folder = mixed_folder(tmp_path)
    service.add_folder(str(folder), "music")
    service.scan()
    assert "id" in service.optimize_media(media_id(str(folder / "movie.mp4")), 200)
    service.save_settings({"version": 1})
    assert not list((tmp_path / "cache/optimized").glob("*.mp4"))


def test_favorites_are_shared_by_url_and_library_removal_clears_both(service):
    url = "https://example.test/video.mp4"
    service.add_favorite("background", url, "Background")
    service.add_favorite("radio", url, "Video")
    service.add_favorite("radio", "https://example.test/stream", "Radio")
    favorites = [entry for entry in service.get_state()["collections"] if entry["kind"] == "favorite"]
    assert [entry["url"] for entry in favorites] == [url, "https://example.test/stream"]
    removed = service.remove_item("library", stable_id("fav", url))
    assert removed["collections"]["favorites"] == []
    assert [entry["url"] for entry in removed["radio"]["favorites"]] == ["https://example.test/stream"]


def test_radio_favorite_keeps_download_after_background_reference_is_removed(service, tmp_path, monkeypatch):
    url = "https://example.test/video.mp4"
    target = tmp_path / "cache" / ("a" * 64 + ".mp4")

    def download(url, directory):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"download")
        return str(target)

    monkeypatch.setattr("ambient.service.download", download)
    service.add_favorite("background", url, "Background")
    service.add_favorite("radio", url, "Video")
    assert "id" in service.cache_remote(url, stable_id("fav", url))
    service.remove_item("background", stable_id("fav", url))
    assert target.exists()
    service.remove_item("radio", stable_id("fav", url))
    assert not target.exists()


def test_removing_pinned_source_keeps_game_reference_and_copy_after_restart(service, tmp_path):
    folder = mixed_folder(tmp_path)
    service.add_folder(str(folder), "library")
    service.scan()
    ref = media_id(str(folder / "movie.mp4"))
    service.optimize_media(ref, 200)
    settings = service.get_state()["settings"]
    settings["background"].update(pinned=ref, perGame={"10": ref})
    service.save_settings(settings)
    reopened = AmbientService(str(tmp_path / "state"), str(tmp_path / "cache"), str(tmp_path / "home"))
    try:
        removed = reopened.remove_item("library", stable_id("folder", str(folder)))
        assert removed["background"]["pinned"] == ""
        assert removed["background"]["perGame"] == {"10": ref}
        assert list((tmp_path / "cache/optimized").glob("*.mp4"))
    finally:
        reopened.close()


def test_overlapping_shared_folder_keeps_pinned_file(service, tmp_path):
    folder = mixed_folder(tmp_path)
    service.add_folder(str(folder), "library")
    service.add_folder(str(folder.parent), "music")
    service.scan()
    ref = media_id(str(folder / "photo.jpg"))
    settings = service.get_state()["settings"]
    settings["background"]["pinned"] = ref
    service.save_settings(settings)
    removed = service.remove_item("library", stable_id("folder", str(folder)))
    assert removed["background"]["pinned"] == ref
    removed = service.remove_item("library", stable_id("folder", str(folder.parent)))
    assert removed["background"]["pinned"] == ""


def test_shared_favorite_removal_clears_pinned_but_not_game_assignment(service):
    url = "https://example.test/a.jpg"
    service.add_favorite("background", url, "a")
    settings = service.add_favorite("radio", url, "a")
    settings["background"].update(pinned="remote:" + url, perGame={"10": "remote:" + url})
    service.save_settings(settings)
    removed = service.remove_item("library", stable_id("fav", url))
    assert removed["background"]["pinned"] == ""
    assert removed["background"]["perGame"] == {"10": "remote:" + url}


@pytest.mark.parametrize("filename", ["photo.jpg", "movie.mp4"])
def test_game_assignment_serves_original_and_copy_after_source_removal_and_restart(service, tmp_path, monkeypatch, filename):
    monkeypatch.setattr(service, "media_url", AmbientService.media_url.__get__(service))
    folder = mixed_folder(tmp_path)
    service.add_folder(str(folder), "library")
    service.scan()
    ref = media_id(str(folder / filename))
    copies = {ref: b"original"}
    if filename.endswith("mp4"):
        copies[service.optimize_media(ref, 200)["id"]] = b"converted"
    settings = service.get_state()["settings"]
    settings["background"]["perGame"] = {"10": ref}
    service.save_settings(settings)
    service.remove_item("library", stable_id("folder", str(folder)))
    service.scan()
    reopened = AmbientService(str(tmp_path / "state"), str(tmp_path / "cache"), str(tmp_path / "home"))
    try:
        reopened.scan()
        for consumer in (service, reopened):
            for reference, contents in copies.items():
                url = consumer.media_url(reference)
                assert url is not None
                with urllib.request.urlopen(url, timeout=3) as response:
                    assert response.read() == contents
            assert consumer.media_url(media_id(str(folder / "song.mp3"))) is None
        reopened.save_settings({"version": 1})
        assert reopened.media_url(ref) is None
    finally:
        reopened.close()


def test_removing_suggested_source_clears_its_pin_but_preserves_other_owners(service, tmp_path, monkeypatch):
    url = "https://example.test/daily.jpg"
    target = tmp_path / "cache" / ("b" * 64 + ".jpg")

    def download(url, directory):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"daily")
        return str(target)

    monkeypatch.setattr("ambient.service.download", download)
    service.cache_remote(url, "suggested.nasa")
    settings = service.get_state()["settings"]
    settings["background"].update(pinned="remote:" + url, collections=["suggested.nasa"], perGame={"10": "remote:" + url})
    service.save_settings(settings)
    removed = service.remove_item("background", "suggested.nasa")
    assert removed["background"]["pinned"] == ""
    assert removed["background"]["perGame"] == {"10": "remote:" + url}
    assert target.exists()


def test_favorite_dedup_and_removal_accept_legacy_different_ids(service):
    url = "https://example.test/shared.mp4"
    settings = service.get_state()["settings"]
    settings["collections"]["favorites"] = [{"id": "fav.old-bg", "name": "Background", "url": url}]
    settings["radio"]["favorites"] = [{"id": "fav.old-radio", "name": "Radio", "url": url}]
    service.save_settings(settings)
    entries = [entry for entry in service.get_state()["collections"] if entry["kind"] == "favorite"]
    assert [entry["id"] for entry in entries] == ["fav.old-bg"]
    removed = service.remove_item("library", "fav.old-bg")
    assert removed["collections"]["favorites"] == []
    assert removed["radio"]["favorites"] == []


def test_assigned_file_replaced_with_symlink_is_not_served(service, tmp_path):
    folder = mixed_folder(tmp_path)
    service.add_folder(str(folder), "library")
    service.scan()
    original = folder / "photo.jpg"
    ref = media_id(str(original))
    settings = service.get_state()["settings"]
    settings["background"]["perGame"] = {"10": ref}
    service.save_settings(settings)
    original.unlink()
    original.symlink_to(folder / "movie.mp4")
    assert AmbientService.media_url(service, ref) is None


def test_source_persistence_failure_is_logged_without_saving_unresolvable_assignment(service, tmp_path, monkeypatch):
    folder = mixed_folder(tmp_path)
    service.add_folder(str(folder), "library")
    service.scan()
    settings = service.get_state()["settings"]
    settings["background"]["perGame"] = {"10": media_id(str(folder / "photo.jpg"))}

    def full(path, contents):
        raise OSError(errno.ENOSPC, "full")

    monkeypatch.setattr("ambient.service.atomic_json_save", full)
    with pytest.raises(OSError):
        service.save_settings(settings)
    assert service.get_state()["settings"]["background"]["perGame"] == {}
    assert any(event["detail"] == "sources:no_space" for event in service.diagnostics()["events"])


def test_explicit_photo_selection_serves_only_selected_originals_after_folder_removal_and_restart(service, tmp_path, monkeypatch):
    monkeypatch.setattr(service, "media_url", AmbientService.media_url.__get__(service))
    folder = mixed_folder(tmp_path)
    second = folder / "other.png"
    second.write_bytes(b"second")
    service.add_folder(str(folder), "library")
    service.scan()
    first_ref, second_ref = media_id(str(folder / "photo.jpg")), media_id(str(second))
    settings = service.get_state()["settings"]
    settings["background"]["selectedRefs"] = [second_ref, first_ref]
    service.save_settings(settings)
    service.remove_item("library", stable_id("folder", str(folder)))
    service.scan()
    reopened = AmbientService(str(tmp_path / "state"), str(tmp_path / "cache"), str(tmp_path / "home"))
    try:
        reopened.scan()
        assert reopened.get_state()["settings"]["background"]["selectedRefs"] == [second_ref, first_ref]
        for consumer in (service, reopened):
            for reference, expected in ((first_ref, b"original"), (second_ref, b"second")):
                url = consumer.media_url(reference)
                assert url is not None
                with urllib.request.urlopen(url, timeout=3) as response:
                    assert response.read() == expected
            assert consumer.media_url(media_id(str(folder / "movie.mp4"))) is None
        updated = reopened.get_state()["settings"]
        updated["background"]["selectedRefs"] = []
        reopened.save_settings(updated)
        assert reopened.media_url(first_ref) is None
        assert reopened.media_url(second_ref) is None
        assert second.read_bytes() == b"second"
        assert (folder / "photo.jpg").read_bytes() == b"original"
    finally:
        reopened.close()


def test_selected_remote_photo_keeps_copy_until_last_selection_and_game_reference_are_removed(service, tmp_path, monkeypatch):
    url = "https://example.test/selected.jpg"
    ref = "remote:" + url
    target = tmp_path / "cache" / ("c" * 64 + ".jpg")

    def download(url, directory):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"selected")
        return str(target)

    monkeypatch.setattr("ambient.service.download", download)
    service.add_favorite("background", url, "Selected")
    settings = service.get_state()["settings"]
    settings["background"].update(selectedRefs=[ref], perGame={"10": ref})
    service.save_settings(settings)
    service.cache_remote(url, stable_id("fav", url))
    service.remove_item("library", stable_id("fav", url))
    updated = service.get_state()["settings"]
    updated["background"]["perGame"] = {}
    service.save_settings(updated)
    assert target.exists()
    updated["background"]["selectedRefs"] = []
    service.save_settings(updated)
    assert not target.exists()


def test_explicit_selection_count_is_reported(service):
    assert service.diagnostics()["selectedBackgroundCount"] == 0
    settings = service.get_state()["settings"]
    settings["background"]["selectedRefs"] = ["steam:10", "steam:20", "steam:10"]
    service.save_settings(settings)
    assert service.diagnostics()["selectedBackgroundCount"] == 2
