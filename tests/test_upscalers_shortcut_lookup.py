"""A non-Steam shortcut is found in shortcuts.vdf alone; it never triggers the search for Steam libraries."""
import struct

from upscalers import games


def _shortcuts(entries: dict[int, tuple[str, str]]) -> bytes:
    blob = b"\0shortcuts\0"
    for index, (appid, (name, exe)) in enumerate(entries.items()):
        blob += b"\0" + str(index).encode() + b"\0"
        blob += b"\2appid\0" + struct.pack("<I", appid)
        blob += b"\1AppName\0" + name.encode() + b"\0"
        blob += b"\1Exe\0" + f'"{exe}"'.encode() + b"\0"
        blob += b"\1StartDir\0" + f'"{exe.rsplit("/", 1)[0]}"'.encode() + b"\0"
        blob += b"\1LaunchOptions\0\0\x08"
    return blob + b"\x08\x08"


def test_a_shortcut_is_found_without_searching_drives_for_steam_libraries(tmp_path, monkeypatch):
    home = tmp_path / "home"
    app = home / "Games/Tool"
    app.mkdir(parents=True)
    (app / "tool.AppImage").write_bytes(b"\x7fELF")
    config = home / ".steam/steam/userdata/1000/config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(_shortcuts({3207429200: ("Tool", f"{app}/tool.AppImage")}))
    (home / ".steam/steam/steamapps").mkdir(parents=True)

    def forbidden(_home):
        raise AssertionError("drives were searched for a shortcut")

    monkeypatch.setattr(games, "_discover", forbidden)
    found = games.find_installed(str(home), "3207429200")
    assert found is not None and (found.shortcut, found.name) == (True, "Tool")
    assert games.find_installed(str(home), "3207429201") is None
