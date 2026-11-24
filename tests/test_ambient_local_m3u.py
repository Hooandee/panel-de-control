import os
from pathlib import Path

import pytest

from ambient.adapters.library_scan import scan_folder
from ambient.core.m3u import parse_m3u
from ambient.core.media_types import media_kind
from ambient.service import AmbientService

FIXTURE = Path(__file__).parent / "fixtures" / "local_channels.m3u8"


def test_parse_hands_non_http_entries_to_the_local_resolver():
    seen = []

    def local(entry):
        seen.append(entry)
        return {"url": "http://127.0.0.1/media/x", "key": "x"} if entry == "radio/otro.ogg" else None

    channels = parse_m3u(FIXTURE.read_text(), local=local)
    assert [c["name"] for c in channels] == ["Canal 1", "Canal 2", "Relativa"]
    assert channels[2]["url"] == "http://127.0.0.1/media/x"
    assert channels[2]["group"] == "Radios"
    assert "../secreto/clave.mp3" in seen


def test_parse_without_resolver_keeps_http_only():
    assert [c["name"] for c in parse_m3u(FIXTURE.read_text())] == ["Canal 1", "Canal 2"]


def test_scan_finds_list_files_but_they_are_never_media(tmp_path):
    (tmp_path / "a.m3u").write_text("#EXTM3U\n")
    (tmp_path / "b.M3U8").write_text("#EXTM3U\n")
    (tmp_path / ".hidden.m3u").write_text("#EXTM3U\n")
    (tmp_path / "song.mp3").write_bytes(b"x")
    found = scan_folder(str(tmp_path), kinds={"list"})
    assert sorted(i["name"] for i in found.items) == ["a.m3u", "b.M3U8"]
    assert {i["kind"] for i in found.items} == {"list"}
    assert media_kind("a.m3u") is None


@pytest.fixture
def library(tmp_path):
    home = tmp_path / "home"
    folder = home / "Listas"
    (folder / "radio").mkdir(parents=True)
    (home / "secreto").mkdir()
    (folder / "radio" / "tema.mp3").write_bytes(b"a")
    (folder / "radio" / "otro.ogg").write_bytes(b"b")
    (home / "secreto" / "clave.mp3").write_bytes(b"c")
    os.symlink(home / "secreto" / "clave.mp3", folder / "radio" / "escape.mp3")
    (folder / "tv.m3u8").write_text(FIXTURE.read_text())
    service = AmbientService(str(tmp_path / "state"), str(tmp_path / "cache"), str(home))
    service.media_url = lambda media: "http://127.0.0.1/media/" + media  # type: ignore[method-assign]
    service.add_folder(str(folder), "music")
    yield service, folder
    service.close()


def test_a_list_in_a_chosen_folder_is_offered_and_read(library):
    service, folder = library
    lists = service.scan()["lists"]
    assert [item["name"] for item in lists] == ["tv.m3u8"]
    contents = service.playlist(lists[0]["id"])
    assert "error" not in contents
    names = [c["name"] for c in contents["channels"]]
    assert names == ["Canal 1", "Canal 2", "Radio Local", "Relativa"]
    local = [c for c in contents["channels"] if c["url"].startswith("http://127.0.0.1/media/local:")]
    assert len(local) == 2


def test_entries_cannot_leave_the_chosen_folder(library):
    service, _ = library
    contents = service.playlist(service.scan()["lists"][0]["id"])
    urls = " ".join(c["url"] for c in contents["channels"])
    assert "passwd" not in urls and "clave" not in urls and "escape" not in urls
    assert all(c["url"].startswith(("https://", "http://127.0.0.1/media/local:")) for c in contents["channels"])


def test_unknown_or_unchosen_local_lists_are_refused(library, tmp_path):
    service, _ = library
    service.scan()
    stray = tmp_path / "home" / "stray.m3u"
    stray.write_text("#EXTM3U\nhttps://x.example.test/a\n")
    from ambient.adapters.library_scan import media_id

    assert service.playlist(media_id(str(stray)))["error"] == "unknown_playlist"
    assert service.playlist("local:nope")["error"] == "unknown_playlist"


def test_a_list_that_became_a_symlink_out_of_the_folder_is_not_read(library, tmp_path):
    service, folder = library
    lists = service.scan()["lists"]
    outside = tmp_path / "home" / "secreto" / "otra.m3u8"
    outside.write_text("#EXTM3U\n#EXTINF:-1,X\nhttps://x.example.test/a\n")
    target = folder / "tv.m3u8"
    target.unlink()
    os.symlink(outside, target)
    assert service.playlist(lists[0]["id"])["error"] == "unknown_playlist"


def test_oversized_local_list_is_refused(library):
    service, folder = library
    lists = service.scan()["lists"]
    (folder / "tv.m3u8").write_bytes(b"#" * (9 * 1024 * 1024))
    assert service.playlist(lists[0]["id"])["error"] == "unreachable"


def test_a_listed_file_that_the_scan_has_not_indexed_is_still_served(library):
    service, folder = library
    lists = service.scan()["lists"]
    (folder / "radio" / "nuevo.mp3").write_bytes(b"n")
    (folder / "tv.m3u8").write_text("#EXTM3U\n#EXTINF:-1,Nuevo\nradio/nuevo.mp3\n")
    del service.media_url  # use the real resolver
    service._ensure_server = lambda: True  # type: ignore[method-assign]
    service._server = type("S", (), {
        "url_for": staticmethod(lambda media: "http://127.0.0.1/media/" + media),
        "stop": staticmethod(lambda: None),
    })()
    contents = service.playlist(lists[0]["id"])
    assert [c["name"] for c in contents["channels"]] == ["Nuevo"]
