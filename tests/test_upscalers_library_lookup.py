import json
import logging
from pathlib import Path

import pytest

from upscalers.service import UpscalerError, UpscalerService


APPID = "870780"
GAME_NAME = "Control"


@pytest.fixture
def steam_install(tmp_path):
    home = tmp_path / "private-home"
    steamapps = home / ".local/share/Steam/steamapps"
    steamapps.mkdir(parents=True)
    service = UpscalerService(
        str(home),
        str(tmp_path / "state"),
        "rdna2",
        logger=logging.getLogger(__name__),
        proc=str(tmp_path / "proc"),
    )
    return service, steamapps


def _write_index(steamapps, entries):
    (steamapps / "libraryfolders.vdf").write_text(f'"libraryfolders" {{ {entries} }}')


def _write_manifest(steamapps):
    steamapps.mkdir(parents=True, exist_ok=True)
    (steamapps / f"appmanifest_{APPID}.acf").write_text(
        f'"AppState" {{ "appid" "{APPID}" "name" "{GAME_NAME}" "installdir" "{GAME_NAME}" "StateFlags" "4" }}'
    )


def _install(steamapps):
    _write_manifest(steamapps)
    game = steamapps / "common" / GAME_NAME
    game.mkdir(parents=True)
    (game / "Control.exe").write_bytes(b"MZ" + b"\0" * 64)


@pytest.mark.parametrize("entry_format", ["direct_path", "path_object"])
def test_game_resolves_a_secondary_steam_library(tmp_path, steam_install, entry_format):
    service, steamapps = steam_install
    secondary = tmp_path / "private-secondary"
    _install(secondary / "steamapps")
    entry = f'"{secondary}"' if entry_format == "direct_path" else f'{{ "path" "{secondary}" }}'
    _write_index(steamapps, f'"1" {entry}')

    game = service.game(APPID)

    assert game["appid"] == APPID
    assert game["name"] == GAME_NAME
    assert game["shortcut"] is False
    assert service.report()["steam_libraries"][entry_format] == 1
    assert service.diagnose(APPID)["steam_lookup"]["found"] == 1


def test_mixed_library_index_ignores_nonnumeric_metadata(tmp_path, steam_install):
    service, steamapps = steam_install
    secondary = tmp_path / "private-secondary"
    metadata = tmp_path / "private-metadata"
    (secondary / "steamapps").mkdir(parents=True)
    _install(metadata / "steamapps")
    _write_index(
        steamapps,
        f'"0" {{ "path" "{steamapps.parent}" }} "1" "{secondary}" '
        f'"contentstatsid" "{metadata}" "metadata" {{ "path" "{metadata}" }}',
    )

    with pytest.raises(UpscalerError) as refused:
        service.game(APPID)

    assert refused.value.code == "not_installed"
    libraries = service.report()["steam_libraries"]
    assert libraries["direct_path"] == 1
    assert libraries["path_object"] == 1
    assert libraries["available"] == 2
    assert service.diagnose(APPID)["steam_lookup"]["manifest_missing"] == 2


@pytest.mark.parametrize("reason", ["missing_index", "invalid_index", "unreadable_index"])
def test_library_index_errors_preserve_the_default_steam_library(steam_install, reason):
    service, steamapps = steam_install
    alias = Path(service.home) / ".steam/steam"
    alias.parent.mkdir()
    alias.symlink_to("steam")
    index = steamapps / "libraryfolders.vdf"
    _install(steamapps)
    if reason == "invalid_index":
        index.write_text('"libraryfolders" {')
    elif reason == "unreadable_index":
        index.mkdir()

    assert service.game(APPID)["name"] == GAME_NAME
    libraries = service.report()["steam_libraries"]
    assert libraries[reason] == 1
    assert libraries["available"] == 1


def test_uninstalled_game_records_steam_lookup_failures_without_paths(tmp_path, steam_install, caplog):
    service, steamapps = steam_install
    corrupt = tmp_path / "private-corrupt"
    absent = tmp_path / "private-missing-folder"
    (corrupt / "steamapps").mkdir(parents=True)
    (corrupt / "steamapps" / f"appmanifest_{APPID}.acf").write_text('"AppState" {')
    _write_manifest(absent / "steamapps")
    _write_index(
        steamapps,
        f'"0" {{ "path" "{steamapps.parent}" }} "1" "{corrupt}" "2" {{ "path" "{absent}" }}',
    )

    with caplog.at_level(logging.INFO, logger=__name__), pytest.raises(UpscalerError) as refused:
        service.game(APPID)

    assert refused.value.code == "not_installed"
    for label in ("direct_path", "path_object", "manifest_missing", "manifest_invalid", "folder_missing"):
        assert label in caplog.text
    assert APPID in caplog.text

    lookup = service.diagnose(APPID)["steam_lookup"]
    for reason in ("manifest_missing", "manifest_invalid", "folder_missing"):
        assert lookup[reason] == 1
    assert lookup.get("found", 0) == 0
    libraries = service.report()["steam_libraries"]
    for private in ("private-home", "private-corrupt", "private-missing-folder"):
        assert private not in caplog.text
        assert private not in json.dumps(lookup)
        assert private not in json.dumps(libraries)
