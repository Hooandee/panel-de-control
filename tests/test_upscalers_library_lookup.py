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


@pytest.mark.parametrize("index", [
    '"libraryfolders" {{ "1" {{ "path" "{lib}" "apps" {{ "870780" "1" "870780" "1" }} }} }}',
    '"libraryfolders" {{ "1" {{ "path" "{lib}" "label" "SD\udce9" }} }}',
])
def test_index_the_strict_reader_refuses_still_yields_its_libraries(tmp_path, steam_install, index):
    service, steamapps = steam_install
    secondary = tmp_path / "private-secondary"
    _install(secondary / "steamapps")
    (steamapps / "libraryfolders.vdf").write_bytes(index.format(lib=secondary).encode("utf-8", "surrogateescape"))

    assert service.game(APPID)["name"] == GAME_NAME
    lookup = service.diagnose(APPID)["steam_lookup"]
    assert lookup["invalid_index"] == 1
    assert lookup["found_lenient_index"] == 1


def test_library_steam_lists_is_used_when_the_index_omits_it(tmp_path, steam_install):
    service, steamapps = steam_install
    secondary = tmp_path / "private-secondary"
    _install(secondary / "steamapps")
    _write_index(steamapps, f'"0" {{ "path" "{steamapps.parent}" }}')

    with pytest.raises(UpscalerError):
        service.game(APPID)
    assert APPID in service.compatibility([APPID], [str(secondary)])
    assert service.game(APPID)["name"] == GAME_NAME
    lookup = service.diagnose(APPID)["steam_lookup"]
    assert lookup["steam_unindexed"] == 1
    assert lookup["found_steam"] == 1


def test_manifest_the_strict_reader_refuses_still_resolves(tmp_path, steam_install):
    service, steamapps = steam_install
    _install(steamapps)
    (steamapps / f"appmanifest_{APPID}.acf").write_text(
        f'"AppState" {{ "appid" "{APPID}" "name" "{GAME_NAME}" "installdir" "{GAME_NAME}" "StateFlags" "4" '
        '"UserConfig" { "language" "english" "Language" "english" } }'
    )

    assert service.game(APPID)["name"] == GAME_NAME


def test_compatibility_learns_the_libraries_steam_lists(tmp_path, steam_install):
    service, steamapps = steam_install
    secondary = tmp_path / "private-secondary"
    _install(secondary / "steamapps")

    assert APPID not in service.compatibility([APPID])
    assert APPID in service.compatibility([APPID], [str(secondary), "relative/path", 7])
    assert APPID not in service.compatibility([APPID], [])


def test_unlisted_library_on_a_mounted_drive_is_discovered(tmp_path, steam_install, monkeypatch):
    from upscalers import games

    service, steamapps = steam_install
    media = tmp_path / "private-media"
    _install(media / "deck" / "SD card" / "steamapps")
    monkeypatch.setattr(games, "MOUNT_ROOTS", (str(media),))

    assert service.game(APPID)["name"] == GAME_NAME
    lookup = service.diagnose(APPID)["steam_lookup"]
    assert lookup["discovered"] == 1
    assert lookup["found_discovery"] == 1
    assert "private-media" not in json.dumps(service.report()["steam_libraries"])


def test_refused_game_carries_the_lookup_for_the_diary(steam_install):
    service, _steamapps = steam_install

    with pytest.raises(UpscalerError) as refused:
        service.game(APPID)

    assert refused.value.lookup["available"] == 1
    assert refused.value.lookup["manifest_missing"] == 1


def test_stale_copy_on_a_drive_never_beats_the_install_steam_knows(tmp_path, steam_install, monkeypatch):
    from upscalers import games

    service, steamapps = steam_install
    _write_manifest(steamapps)  # Steam's own record, its folder gone while the game moves
    backup = tmp_path / "private-media"
    _install(backup / "backup" / "SteamLibrary" / "steamapps")
    monkeypatch.setattr(games, "MOUNT_ROOTS", (str(backup),))

    with pytest.raises(UpscalerError) as refused:
        service.game(APPID)
    assert refused.value.lookup["folder_missing"] == 1
    assert "found_discovery" not in refused.value.lookup


def test_one_library_reached_through_two_paths_counts_once(tmp_path, steam_install, monkeypatch):
    from upscalers import games

    service, steamapps = steam_install
    media = tmp_path / "private-media"
    card = media / "deck" / "SD"
    (card / "steamapps").mkdir(parents=True)
    alias = tmp_path / "private-mmcblk0p1"
    alias.symlink_to(card)
    _write_index(steamapps, f'"1" {{ "path" "{alias}" }}')
    games.set_steam_libraries([str(card), f"{card}/../SD"])
    monkeypatch.setattr(games, "MOUNT_ROOTS", (str(media),))

    assert games.library_paths(service.home) == [steamapps.parent, card.resolve()]


def test_steam_library_list_is_replaced_not_accumulated(tmp_path, steam_install):
    from upscalers import games

    service, _steamapps = steam_install
    first, second = tmp_path / "private-a", tmp_path / "private-b"
    for library in (first, second):
        (library / "steamapps").mkdir(parents=True)
    service.compatibility([], [str(first)])
    service.compatibility([], [str(second)])

    assert first.resolve() not in games.library_paths(service.home)
    assert second.resolve() in games.library_paths(service.home)


def test_discovery_skips_network_shares(tmp_path, monkeypatch):
    from upscalers import games

    share, local = tmp_path / "private-nfs", tmp_path / "private-disk"
    for library in (share, local):
        (library / "Games" / "steamapps").mkdir(parents=True)
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(f"36 25 0:52 / {share} rw - nfs4 server:/export rw\n37 25 8:1 / {local} rw - ext4 /dev/sda1 rw\n")
    read = games._network_mounts
    monkeypatch.setattr(games, "_network_mounts", lambda: read(str(mountinfo)))
    monkeypatch.setattr(games, "MOUNT_ROOTS", (str(share), str(local)))

    assert games._discover(str(tmp_path / "private-home")) == [(local / "Games").resolve()]


def test_discovery_reaches_network_shares_through_a_linked_mount_root_and_skips_them(tmp_path, monkeypatch):
    from upscalers import games

    real = tmp_path / "private-var-mnt"
    (real / "nas" / "Games" / "steamapps").mkdir(parents=True)
    (real / "disk" / "Games" / "steamapps").mkdir(parents=True)
    linked = tmp_path / "private-mnt"
    linked.symlink_to(real)
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(f"36 25 0:52 / {real.resolve()}/nas rw - nfs4 server:/export rw\n")
    read = games._network_mounts
    monkeypatch.setattr(games, "_network_mounts", lambda: read(str(mountinfo)))
    monkeypatch.setattr(games, "MOUNT_ROOTS", (str(linked),))

    assert games._discover(str(tmp_path / "private-home")) == [(real / "disk" / "Games").resolve()]


def test_discovered_game_folder_linking_outside_its_library_is_refused(tmp_path, steam_install, monkeypatch):
    from upscalers import games

    service, _steamapps = steam_install
    media = tmp_path / "private-media"
    apps = media / "usb" / "steamapps"
    _write_manifest(apps)
    elsewhere = tmp_path / "private-elsewhere"
    elsewhere.mkdir()
    (apps / "common").mkdir()
    (apps / "common" / GAME_NAME).symlink_to(elsewhere)
    monkeypatch.setattr(games, "MOUNT_ROOTS", (str(media),))

    with pytest.raises(UpscalerError) as refused:
        service.game(APPID)
    assert refused.value.lookup["discovery_folder_outside"] == 1


def test_lenient_manifest_reads_only_top_level_fields(tmp_path, steam_install):
    service, steamapps = steam_install
    _install(steamapps)
    (steamapps / f"appmanifest_{APPID}.acf").write_text(
        f'"AppState" {{ "appid" "{APPID}" "name" "{GAME_NAME}" "installdir" "{GAME_NAME}" "StateFlags" "4" '
        '"InstalledDepots" { "1" { "installdir" "Other" "name" "Other" } } "UserConfig" { "x" "1" "X" "1" } }'
    )

    assert service.game(APPID)["name"] == GAME_NAME


def test_selector_confirms_fully_installed_manifest_in_accessible_secondary_library(tmp_path, steam_install):
    service, apps = steam_install
    secondary = tmp_path / "second"
    missing = tmp_path / "missing"
    folder = secondary / "steamapps"
    (folder / "common" / "Resident Evil Requiem").mkdir(parents=True)
    _write_index(apps, f'"0" {{ "path" "{apps.parent}" }} "1" {{ "path" "{secondary}" }} "2" {{ "path" "{missing}" }}')
    for appid, flags, directory in [("3764200", 4, "Resident Evil Requiem"), ("10", 1024, "Resident Evil Requiem"),
                                    ("20", 4, "Removed"), ("30", 4, "..")]:
        (folder / f"appmanifest_{appid}.acf").write_text(
            f'"AppState" {{ "appid" "{appid}" "StateFlags" "{flags}" "installdir" "{directory}" }}'
        )

    from upscalers import games

    assert games.selector_installs(service.home) == {"appids": [3764200], "complete": False}
    _write_index(apps, f'"0" {{ "path" "{apps.parent}" }}')
    assert games.selector_installs(service.home, (str(secondary),)) == {"appids": [3764200], "complete": True}


def test_selector_skips_nonregular_index_and_partial_manifest_without_waiting(steam_install):
    import os
    from upscalers import games

    service, apps = steam_install
    os.mkfifo(apps / "libraryfolders.vdf")
    os.mkfifo(apps / "appmanifest_20.acf")
    _install(apps)
    assert games.selector_installs(service.home) == {"appids": [int(APPID)], "complete": False}
