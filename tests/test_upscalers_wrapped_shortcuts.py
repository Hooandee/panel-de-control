"""Shortcuts that reach a Windows game through a script: PortProton, Unifideck and hand-written wrappers."""
from pathlib import Path

import pytest

from upscalers import games, launchers


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ" + b"\0" * 64)
    return path


def _script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)
    return path


def _portproton(home, flatpak=False):
    game = _exe(home / "Games/Ghost of Tsushima/GhostOfTsushima.exe")
    runner = "flatpak run ru.linux_gaming.PortProton" if flatpak else f'"{home}/PortProton/data/scripts/start.sh"'
    script = _script(home / "PortProton/steam_scripts/Ghost Of Tsushima.sh",
                     f'export LD_PRELOAD=\nexport START_FROM_STEAM=1\nexport START_FROM_FLATPAK=0\n{runner} "{game}" "$@"\n')
    found = games.from_hint("3520677033", {"exe": f'"{script}"', "dir": str(script.parent), "name": "Ghost Of Tsushima", "opts": ""}, str(home))
    return game, script, found


@pytest.mark.parametrize("flatpak", [False, True])
def test_a_portproton_script_leads_to_its_game(home, flatpak):
    game, script, found = _portproton(home, flatpak)
    assert (found.native, found.shortcut, found.root, found.exe) == (False, True, game.parent, "GhostOfTsushima.exe")
    assert found.launcher == ("portproton", str(script), None)


def test_portproton_overrides_go_in_the_games_ppdb_and_come_back_out(home):
    game, _, found = _portproton(home)
    profile = game.with_name(game.name + ".ppdb")
    profile.write_text('#!/usr/bin/env bash\n#GhostOfTsushima.exe\nexport PW_VULKAN_USE="2"\nexport WINEDLLOVERRIDES="mfc120=b,n"\n')
    launched = launchers.find(str(home), *found.launcher)
    launchers.set_overrides(launched, ["dxgi", "winmm"])
    assert 'export WINEDLLOVERRIDES="mfc120=b,n;dxgi,winmm=n,b"' in profile.read_text()
    assert 'export PW_VULKAN_USE="2"' in profile.read_text()
    launchers.set_overrides(launched, ["dxgi", "winmm"], remove=True)
    assert 'export WINEDLLOVERRIDES="mfc120=b,n"' in profile.read_text()


def test_a_portproton_game_without_profile_starts_from_portprotons_own(home):
    game, _, found = _portproton(home)
    database = home / "PortProton/data/scripts/portwine_db"
    database.mkdir(parents=True)
    (database / "GoT").write_text('#!/usr/bin/env bash\n#GhostOfTsushima.exe\nexport PW_WINE_USE="PROTON_LG"\n')
    launched = launchers.find(str(home), *found.launcher)
    launchers.set_overrides(launched, ["dxgi"], remove=True)
    assert not launched.config.exists()
    launchers.set_overrides(launched, ["dxgi"])
    text = launched.config.read_text()
    assert 'export PW_WINE_USE="PROTON_LG"' in text and text.rstrip().endswith('export WINEDLLOVERRIDES="dxgi=n,b"')


def test_unifidecks_older_map_format_is_read_too(home):
    game = _exe(home / "GOG Games/Old/old.exe")
    (home / ".local/share/unifideck").mkdir(parents=True)
    (home / launchers.UNIFIDECK_MAP).write_text(f"gog:1207658924|{game}|{game.parent}\n")
    assert launchers.wrapped_exe(str(home), "/x/unifideck-launcher", "gog:1207658924 MANGOHUD=1") == game


def test_a_wrapper_passed_after_the_command_is_followed(home):
    game = _exe(home / "Games/StellarBlade/SB/Binaries/Win64/SB-Win64-Shipping.exe")
    (home / "Games/StellarBlade/Engine").mkdir()
    script = _script(home / "Games/wrappers/Stellar Blade.sh", "cd \"$HOME/Games/StellarBlade\"\nexec $HOME/Games/StellarBlade/SB/Binaries/Win64/SB-Win64-Shipping.exe\n")
    runner = home / "bin/runner"
    runner.parent.mkdir(parents=True)
    runner.write_bytes(b"\x7fELF")
    found = games.from_hint("3529970468", {"exe": str(runner), "dir": str(runner.parent), "name": "Stellar Blade",
                                           "opts": f'PROTON_USE_OPTISCALER=1 %command% "{script}"'}, str(home))
    assert (found.native, found.root, found.exe) == (False, home / "Games/StellarBlade", "SB/Binaries/Win64/SB-Win64-Shipping.exe")
    assert found.exe == game.relative_to(found.root).as_posix()


def test_a_unifideck_game_is_read_from_its_map(home):
    game = _exe(home / "Games/Epic/Metro Exodus/MetroExodus.exe")
    other = _exe(home / "GOG Games/Other/other.exe")
    (home / ".local/share/unifideck").mkdir(parents=True)
    (home / launchers.UNIFIDECK_MAP).write_text(f"# map\ngog:1234={other}\nepic:abc123DEF={game}\t{game.parent}\t-1234\n")
    launcher = _script(home / "homebrew/plugins/unifideck/bin/unifideck-launcher", "exec something\n")
    found = games.from_hint("2385321951", {"exe": str(launcher), "dir": str(launcher.parent), "name": "Metro Exodus",
                                           "opts": "epic:abc123DEF LSFG=1"}, str(home))
    assert (found.native, found.root, found.exe) == (False, game.parent, "MetroExodus.exe")


@pytest.mark.parametrize("body", ["exec ./game.x86_64\n", 'exec "/nowhere/Missing.exe"\n', 'exec "$GAMEDIR/Game.exe"\n'])
def test_a_script_without_a_windows_game_stays_a_linux_game(home, body):
    script = _script(home / "Games/native/start.sh", body)
    found = games.from_hint("77", {"exe": str(script), "dir": str(script.parent), "name": "Native", "opts": ""}, str(home))
    assert found.native is True and found.exe is None


def test_a_binary_shortcut_is_never_read_as_a_script(home):
    _exe(home / "Games/x/Game.exe")
    binary = home / "Games/x/emulator.AppImage"
    binary.write_bytes(b"\x7fELF" + f'"{home}/Games/x/Game.exe"'.encode())
    found = games.from_hint("78", {"exe": str(binary), "dir": str(binary.parent), "name": "Emu", "opts": ""}, str(home))
    assert found.native is True
