import json
import urllib.request

import pytest

from ambient.service import AmbientService


def _touch(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    _touch(h / "Pictures" / "dunes.jpg", b"JPG")
    _touch(h / "Videos" / "loop.webm", b"WEBM")
    _touch(h / "Music" / "song.mp3", b"MP3")
    _touch(h / "secret.jpg", b"NO")
    return h


@pytest.fixture
def service(tmp_path, home):
    svc = AmbientService(state_dir=str(tmp_path / "state"), cache_dir=str(tmp_path / "cache"), home=str(home))
    yield svc
    svc.close()


def test_state_has_defaults_and_known_folders(service, home):
    state = service.get_state()
    assert state["settings"]["version"] == 1
    assert state["knownFolders"]["images"] == [str(home / "Pictures")]
    ids = [c["id"] for c in state["collections"]]
    assert ids[0] == "known.images"
    assert [i for i in ids if i.startswith("suggested.")] == ["suggested.library", "suggested.nasa", "suggested.bing"]


def test_save_settings_normalizes_and_persists(service, tmp_path, home):
    saved = service.save_settings({"version": 1, "background": {"intervalSec": 61}})
    assert saved["background"]["intervalSec"] == 60
    reopened = AmbientService(state_dir=str(tmp_path / "state"), cache_dir=str(tmp_path / "cache"), home=str(home))
    assert reopened.get_state()["settings"]["background"]["intervalSec"] == 60
    reopened.close()


def test_corrupt_settings_file_falls_back_to_defaults(tmp_path, home):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "settings.json").write_text("{nope")
    svc = AmbientService(state_dir=str(state_dir), cache_dir=str(tmp_path / "cache"), home=str(home))
    assert svc.get_state()["settings"]["background"]["intervalSec"] == 300
    svc.close()


def test_scan_groups_media_by_collection(service):
    result = service.scan()
    assert [m["name"] for m in result["collections"]["known.images"]] == ["dunes.jpg", "loop.webm"]
    assert [m["name"] for m in result["music"]] == ["song.mp3"]
    assert "path" not in result["collections"]["known.images"][0]


def test_media_url_serves_scanned_file(service):
    item = service.scan()["collections"]["known.images"][0]
    url = service.media_url(item["id"])
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.read() == b"JPG"


def test_media_url_refuses_unscanned_ids(service):
    service.scan()
    assert service.media_url("local:0000") is None


def test_user_folder_becomes_collection(service, home):
    _touch(home / "Wall" / "a.png")
    service.add_folder(str(home / "Wall"))
    result = service.scan()
    folder = [c for c in service.get_state()["collections"] if c["kind"] == "folder"][0]
    assert [m["name"] for m in result["collections"][folder["id"]]] == ["a.png"]


def test_add_folder_rejects_non_directories(service, home):
    with pytest.raises(ValueError):
        service.add_folder(str(home / "Pictures" / "dunes.jpg"))


def test_favorites_and_restore(service):
    service.add_favorite("background", "https://x.test/a.jpg", "Cielo")
    service.remove_item("background", "suggested.bing")
    ids = [c["id"] for c in service.get_state()["collections"]]
    assert "suggested.bing" not in ids and any(i.startswith("fav.") for i in ids)
    service.restore_suggested("background")
    assert "suggested.bing" in [c["id"] for c in service.get_state()["collections"]]


def test_events_are_bounded_and_in_diagnostics(service):
    for n in range(40):
        service.record_event("playback_error", f"code{n}")
    diag = service.diagnostics()
    assert len(diag["events"]) == 20
    assert diag["events"][-1]["detail"] == "code39"
    assert diag["mediaServer"] in ("loopback", "stopped")
    assert "home" not in json.dumps(diag)


@pytest.mark.parametrize("detail", ["enter", "exit"])
def test_fullscreen_events_are_recorded(service, detail):
    assert service.record_event("video_fullscreen", detail) is True
    event = service.diagnostics()["events"][-1]
    assert event["kind"] == "video_fullscreen"
    assert event["detail"] == detail


def test_music_folders_are_scanned(service, home):
    _touch(home / "Albums" / "b.flac")
    service.add_folder(str(home / "Albums"), scope="music")
    assert [m["name"] for m in service.scan()["music"]] == ["song.mp3", "b.flac"]


def test_music_folder_can_be_removed_by_its_path(service, home):
    _touch(home / "Albums" / "b.flac")
    service.add_folder(str(home / "Albums"), scope="music")
    folder = service.get_state()["settings"]["music"]["folders"][0]
    assert service.remove_item("music", folder)["music"]["folders"] == []


def test_cache_remote_serves_downloaded_file(service, monkeypatch):
    from ambient.adapters import remote_sources

    def fake_download(url, cache_dir, opener=None, max_bytes=None):
        target = remote_sources.os.path.join(cache_dir, "f" * 64 + ".jpg")
        remote_sources.os.makedirs(cache_dir, exist_ok=True)
        open(target, "wb").write(b"REMOTE")
        return target

    monkeypatch.setattr("ambient.service.download", fake_download)
    cached = service.cache_remote("https://img.test/a.jpg")
    assert cached["id"].startswith("url:")
    with urllib.request.urlopen(cached["url"], timeout=5) as response:
        assert response.read() == b"REMOTE"


def test_optimize_media_indexes_result(service, monkeypatch, tmp_path):
    from ambient.adapters.optimizer import Optimized

    item = service.scan()["collections"]["known.images"][1]
    out = tmp_path / "cache" / "optimized" / "opt-abc.mp4"

    def fake_optimize(source, cache_dir, height, cancel=None, fps=30):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"SMALL")
        assert (height, fps) == (800, 15)
        return Optimized(str(out), "h264_vaapi")

    monkeypatch.setattr("ambient.service.optimize", fake_optimize)
    result = service.optimize_media(item["id"], 800, 15)
    assert result["encoder"] == "h264_vaapi" and result["id"] == "opt:opt-abc"
    assert service.media_url(result["id"]).startswith("http://127.0.0.1:")


def test_optimize_unknown_media(service):
    assert service.optimize_media("local:nope", 800) == {"error": "unknown_media"}


def test_cache_remote_reuses_the_cached_file(service, monkeypatch):
    calls = []

    def fake_download(url, cache_dir, opener=None, max_bytes=None):
        import os
        calls.append(url)
        os.makedirs(cache_dir, exist_ok=True)
        target = os.path.join(cache_dir, "e" * 64 + ".jpg")
        open(target, "wb").write(b"ONCE")
        return target

    monkeypatch.setattr("ambient.service.download", fake_download)
    first = service.cache_remote("https://img.test/b.jpg")
    second = service.cache_remote("https://img.test/b.jpg")
    assert calls == ["https://img.test/b.jpg"]
    assert first["id"] == second["id"]


def test_closed_service_never_starts_the_server(service):
    item = service.scan()["collections"]["known.images"][0]
    service.close()
    assert service.media_url(item["id"]) is None


def test_radio_catalog_is_cached_and_survives_offline(service, monkeypatch):
    from ambient.adapters import radio_browser
    calls = []
    monkeypatch.setattr(radio_browser, "countries", lambda: calls.append("c") or [{"code": "ES", "name": "Spain", "count": 3}])
    monkeypatch.setattr(radio_browser, "tags", lambda: [{"name": "lofi", "count": 9}])
    first = service.radio_catalog()
    assert first["countries"][0]["code"] == "ES"
    service.radio_catalog()
    assert calls == ["c"]
    import json
    import os
    path = os.path.join(service._cache_dir, "radio-catalog.json")
    data = json.load(open(path))
    data["at"] = 0
    json.dump(data, open(path, "w"))
    monkeypatch.setattr(radio_browser, "countries", lambda: [])
    monkeypatch.setattr(radio_browser, "tags", lambda: [])
    assert service.radio_catalog()["tags"] == [{"name": "lofi", "count": 9}]


def test_discover_answers_repeated_queries_from_memory(service, monkeypatch):
    from ambient.adapters import radio_browser
    calls = []
    monkeypatch.setattr(radio_browser, "discover", lambda f: calls.append(f) or [{"id": "s1"}])
    service.discover_radio({"country": "ES", "hasGeo": True})
    service.discover_radio({"hasGeo": True, "country": "ES"})
    service.discover_radio({"country": "FR"})
    assert len(calls) == 2


def test_playlists_are_saved_fetched_cached_and_removed(tmp_path, monkeypatch):
    from ambient.adapters import remote_sources
    from ambient.service import AmbientService

    calls = []

    def fake_fetch(url):
        calls.append(url)
        return "#EXTM3U\n#EXTINF:-1 group-title=\"News\",Canal 24\nhttps://tv.test/24.m3u8\n"

    monkeypatch.setattr(remote_sources, "fetch_text", fake_fetch)
    service = AmbientService(state_dir=str(tmp_path / "state"), cache_dir=str(tmp_path / "cache"), home=str(tmp_path))
    settings = service.add_playlist("https://lists.test/tv.m3u", "TDT")
    playlist = settings["radio"]["playlists"][0]
    assert playlist["name"] == "TDT" and playlist["id"].startswith("list.")
    first = service.playlist(playlist["id"])
    assert [c["name"] for c in first["channels"]] == ["Canal 24"]
    assert service.playlist(playlist["id"])["channels"] == first["channels"]
    assert calls == ["https://lists.test/tv.m3u"]
    assert service.remove_playlist(playlist["id"])["radio"]["playlists"] == []
    assert service.playlist(playlist["id"])["error"] == "unknown_playlist"
    service.close()


def test_game_media_is_looked_up_once_and_remembered(service, monkeypatch):
    calls = []
    monkeypatch.setattr("ambient.service.game_trailer", lambda appid: calls.append(appid) or {"url": "https://video.akamai.steamstatic.com/a.m3u8"})
    monkeypatch.setattr("ambient.service.game_theme", lambda name: None)
    first = service.game_media("10", "Game", now=1000)
    again = service.game_media("10", "Game", now=2000)
    assert first == again == {"trailer": {"url": "https://video.akamai.steamstatic.com/a.m3u8"}, "theme": None}
    assert calls == ["10"]
    service.game_media("10", "Game", now=1000 + 8 * 24 * 3600)
    assert calls == ["10", "10"]


def test_shortcuts_never_ask_the_store(service, monkeypatch):
    monkeypatch.setattr("ambient.service.game_trailer", lambda appid: pytest.fail("store asked for a shortcut"))
    monkeypatch.setattr("ambient.service.game_theme", lambda name: None)
    assert service.game_media("3141592653", "Emulator", store=False) == {"trailer": None, "theme": None}
