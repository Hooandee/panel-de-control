"""A Unifideck library read through shortcuts.vdf and games.map, the way Steam and Unifideck write them."""
import pytest

from upscalers import games
from test_upscalers import _service, steam, fake_catalog, proc, _write  # noqa: F401

LAUNCHER = "homebrew/plugins/unifideck/bin/unifideck-launcher"


def _vdf(entries, twice=()):
    def string(key, value):
        return b"\x01" + key.encode() + b"\0" + value.encode() + b"\0"

    body = b""
    for index, entry in enumerate(entries):
        fields = b"\x02appid\0" + entry["appid"].to_bytes(4, "little") + string("AppName", entry["name"]) \
            + string("Exe", entry["exe"]) + string("StartDir", entry["start"]) + string("LaunchOptions", entry["opts"])
        if index in twice:
            fields += string("exe", entry["exe"]) + string("appname", entry["name"])
        body += b"\x00" + str(index).encode() + b"\0" + fields + b"\x08"
    return b"\x00shortcuts\0" + body + b"\x08\x08"


@pytest.fixture
def library(steam, request):
    home, _ = steam
    launcher = home / LAUNCHER
    _write(launcher, "#!/usr/bin/env bash\nexec true\n")
    windows = _write(home / "Games/unifideck/epic/Space Game/Binaries/Win64/SpaceGame.exe", b"MZ" + b"\0" * 64)
    linux = _write(home / "Games/unifideck/gog/Tiny Rogue/start.sh", "#!/bin/sh\nexec ./tiny\n")
    rows = [
        ("epic:aaa111", windows, "Space Game", 3927458460),
        ("gog:2002", linux, "Tiny Rogue", 3778260273),
        ("ubisoft:3003", "", "Uplay Game", 3223286528),
        ("microsoft:4004", "xcloud", "Cloud Game", 2827650483),
        ("epic:gone", home / "Games/unifideck/epic/Removed/Removed.exe", "Removed Game", 4262835099),
        ("epic:notinstalled", None, "Library Only", 3058439269),
    ]
    text = "# Unifideck non-Steam shortcut manifest (games.map)\n"
    entries = []
    for key, exe, name, appid in rows:
        if exe is not None:
            text += f"{key}={exe}\t{exe.parent if exe and exe != 'xcloud' else ''}\t{appid - 2 ** 32}\n"
        entries.append({"appid": appid, "name": name, "exe": f'"{launcher}"', "start": f'"{launcher.parent}"', "opts": key})
    _write(home / ".local/share/unifideck/games.map", text)
    _write(home / ".local/share/Steam/userdata/123/config/shortcuts.vdf", _vdf(entries, twice=getattr(request, "param", ())))
    return home


def test_an_unifideck_library_is_sorted_into_what_panel_can_act_on(library, steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    result = service.compatibility([str(row) for row in (3927458460, 3778260273, 3223286528, 2827650483, 4262835099, 3058439269)])
    assert result["3927458460"].get("unavailable") is None and result["3927458460"]["native"] is False
    assert result["3778260273"]["native"] is True
    assert result["3223286528"]["unavailable"] == "unifideck_no_exe"
    assert result["2827650483"]["unavailable"] == "unifideck_not_installed"
    assert result["4262835099"]["unavailable"] == "unifideck_missing"
    assert result["3058439269"]["unavailable"] == "unifideck_not_installed"


@pytest.mark.parametrize("library", [(1, 3)], indirect=True)
def test_one_shortcut_listing_its_exe_in_two_cases_does_not_hide_the_whole_library(library, steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    result = service.compatibility(["3927458460", "3778260273", "3223286528"])
    assert result["3927458460"]["native"] is False and result["3778260273"]["native"] is True
    assert result["3223286528"]["unavailable"] == "unifideck_no_exe"
