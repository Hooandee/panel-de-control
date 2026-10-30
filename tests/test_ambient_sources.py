import os

from ambient.adapters.known_paths import known_folders
from ambient.adapters.library_scan import scan_folder
from ambient.adapters.steam_screenshots import screenshot_folders


def _touch(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_known_folders_only_existing(tmp_path):
    (tmp_path / "Pictures").mkdir()
    (tmp_path / "Music").mkdir()
    folders = known_folders(str(tmp_path))
    assert folders == {"images": [str(tmp_path / "Pictures")], "videos": [], "music": [str(tmp_path / "Music")]}


def test_known_folders_accept_localized_xdg_dirs(tmp_path):
    (tmp_path / "Imágenes").mkdir()
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "user-dirs.dirs").write_text('XDG_PICTURES_DIR="$HOME/Imágenes"\n')
    assert known_folders(str(tmp_path))["images"] == [str(tmp_path / "Imágenes")]


def test_scan_lists_media_with_stable_ids(tmp_path):
    _touch(tmp_path / "a.jpg")
    _touch(tmp_path / "sub" / "b.webm")
    _touch(tmp_path / "notes.txt")
    first = scan_folder(str(tmp_path), kinds={"image", "video"})
    second = scan_folder(str(tmp_path), kinds={"image", "video"})
    assert [i["kind"] for i in first.items] == ["image", "video"]
    assert [i["id"] for i in first.items] == [i["id"] for i in second.items]
    assert not first.truncated


def test_scan_filters_by_kind(tmp_path):
    _touch(tmp_path / "a.jpg")
    _touch(tmp_path / "s.mp3")
    assert [i["kind"] for i in scan_folder(str(tmp_path), kinds={"audio"}).items] == ["audio"]


def test_scan_respects_depth_and_limit(tmp_path):
    _touch(tmp_path / "1" / "2" / "3" / "4" / "deep.jpg")
    for n in range(5):
        _touch(tmp_path / f"{n}.jpg")
    result = scan_folder(str(tmp_path), kinds={"image"}, max_depth=3, max_files=3)
    assert len(result.items) == 3
    assert result.truncated
    assert all("deep" not in i["path"] for i in scan_folder(str(tmp_path), kinds={"image"}, max_depth=3).items)


def test_scan_does_not_follow_directory_symlinks(tmp_path):
    outside = tmp_path / "outside"
    _touch(outside / "x.jpg")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    assert scan_folder(str(root), kinds={"image"}).items == []


def test_scan_missing_folder_is_empty(tmp_path):
    result = scan_folder(str(tmp_path / "nope"), kinds={"image"})
    assert result.items == [] and result.missing


def test_screenshot_folders(tmp_path):
    steam = tmp_path / ".local" / "share" / "Steam"
    shots = steam / "userdata" / "123" / "760" / "remote" / "1091500" / "screenshots"
    _touch(shots / "a.jpg")
    _touch(steam / "userdata" / "123" / "760" / "remote" / "1091500" / "screenshots" / "thumbnails" / "a.jpg")
    assert screenshot_folders(str(tmp_path)) == [os.path.realpath(shots)]
