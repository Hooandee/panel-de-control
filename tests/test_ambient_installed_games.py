import importlib
import os

import pytest


def snapshot(home, previous_libraries=None):
    module = importlib.import_module("ambient.adapters.installed_games")
    return module.snapshot(str(home), previous_libraries)


def steam_home(tmp_path):
    home = tmp_path / "home"
    root = home / ".local/share/Steam"
    (root / "steamapps").mkdir(parents=True)
    library_index(root, [root])
    return home, root


def library_index(root, libraries):
    entries = " ".join(f'"{i}" {{ "path" "{path}" "apps" {{}} }}' for i, path in enumerate(libraries))
    (root / "steamapps/libraryfolders.vdf").write_text(f'"libraryfolders" {{ {entries} }}')


def manifest(root, appid="10"):
    (root / "steamapps").mkdir(parents=True, exist_ok=True)
    path = root / f"steamapps/appmanifest_{appid}.acf"
    path.write_text(f'"AppState" {{ "appid" "{appid}" "name" "Example" }}')
    return path


def test_deleted_manifest_confirms_uninstall(tmp_path):
    home, root = steam_home(tmp_path)
    path = manifest(root)
    before = snapshot(home)
    assert before["installed"] == ["10"]
    assert before["complete"] is True
    identity = root.stat()
    assert before["libraries"] == {str(root): [identity.st_dev, identity.st_ino]}
    path.unlink()
    after = snapshot(home, before["libraries"])
    assert after["installed"] == []
    assert after["complete"] is True


def test_empty_home_is_incomplete(tmp_path):
    assert snapshot(tmp_path)["complete"] is False


def test_missing_library_index_is_incomplete(tmp_path):
    home, root = steam_home(tmp_path)
    (root / "steamapps/libraryfolders.vdf").unlink()
    assert snapshot(home)["complete"] is False


def test_disconnected_library_survives_its_removal_from_index(tmp_path):
    home, root = steam_home(tmp_path)
    card = tmp_path / "card"
    manifest(card)
    library_index(root, [root, card])
    before = snapshot(home)
    assert before["complete"] is True
    card.rename(tmp_path / "unmounted-card")
    library_index(root, [root])
    after = snapshot(home, before["libraries"])
    assert after["complete"] is False
    assert after["libraries"] == before["libraries"]


def test_replaced_library_identity_is_incomplete(tmp_path):
    home, root = steam_home(tmp_path)
    before = snapshot(home)
    root.rename(root.with_name("old-Steam"))
    (root / "steamapps").mkdir(parents=True)
    library_index(root, [root])
    after = snapshot(home, before["libraries"])
    assert after["complete"] is False
    assert after["libraries"] == before["libraries"]


def test_unreadable_library_is_incomplete(tmp_path, monkeypatch):
    home, root = steam_home(tmp_path)
    real_scandir = os.scandir

    def scandir(path):
        if str(path) == str(root / "steamapps"):
            raise PermissionError("unreadable")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", scandir)
    assert snapshot(home)["complete"] is False


def test_newly_discovered_missing_library_is_incomplete(tmp_path):
    home, root = steam_home(tmp_path)
    library_index(root, [root, tmp_path / "missing-card"])
    assert snapshot(home)["complete"] is False


def test_unreadable_manifest_is_not_reported_as_absent(tmp_path, monkeypatch):
    home, root = steam_home(tmp_path)
    path = manifest(root)
    real_open = os.open

    def open_file(target, *args, **kwargs):
        if str(target) == str(path):
            raise PermissionError("unreadable")
        return real_open(target, *args, **kwargs)

    monkeypatch.setattr(os, "open", open_file)
    assert snapshot(home)["complete"] is False


@pytest.mark.parametrize("contents", [
    '"libraryfolders" {',
    '"libraryfolders" {} ignored',
    '"libraryfolders" { "0" { "path" "relative" } }',
    '"libraryfolders" { "0" {} }',
    '"libraryfolders" {} "libraryfolders" {}',
])
def test_corrupt_library_index_is_incomplete(tmp_path, contents):
    home, root = steam_home(tmp_path)
    (root / "steamapps/libraryfolders.vdf").write_text(contents)
    assert snapshot(home)["complete"] is False


@pytest.mark.parametrize("contents", [
    '',
    '"AppState" { "appid" "20" }',
    '"AppState" { "appid" "10" "appid" "20" }',
    '"AppState" { "appid" "10" } trailing',
    '"AppState" { "appid" "2147483648" }',
])
def test_ambiguous_manifest_is_incomplete(tmp_path, contents):
    home, root = steam_home(tmp_path)
    manifest(root).write_text(contents)
    assert snapshot(home)["complete"] is False


def test_moving_game_between_libraries_preserves_installation(tmp_path):
    home, root = steam_home(tmp_path)
    card = tmp_path / "card"
    (card / "steamapps").mkdir(parents=True)
    library_index(root, [root, card])
    path = manifest(root)
    before = snapshot(home)
    path.rename(card / path.relative_to(root))
    after = snapshot(home, before["libraries"])
    assert after["installed"] == ["10"]
    assert after["complete"] is True


def test_game_moved_during_inventory_cannot_be_reported_uninstalled(tmp_path, monkeypatch):
    home, root = steam_home(tmp_path)
    card = tmp_path / "card"
    (card / "steamapps").mkdir(parents=True)
    library_index(root, [root, card])
    path = manifest(root)
    before = snapshot(home)
    real_scandir = os.scandir

    def scandir(directory):
        if str(directory) == str(root / "steamapps"):
            path.rename(card / path.relative_to(root))
        return real_scandir(directory)

    monkeypatch.setattr(os, "scandir", scandir)
    after = snapshot(home, before["libraries"])
    assert after["installed"] == []
    assert after["complete"] is False


def test_inventory_has_no_sixty_game_limit(tmp_path):
    home, root = steam_home(tmp_path)
    for appid in range(1, 76):
        manifest(root, str(appid))
    result = snapshot(home)
    assert result["installed"] == [str(appid) for appid in range(1, 76)]
    assert result["complete"] is True


def test_non_steam_manifest_cannot_authorize_cleanup(tmp_path):
    home, root = steam_home(tmp_path)
    manifest(root, "3000000000")
    result = snapshot(home)
    assert result["installed"] == []
    assert result["complete"] is False


def test_comments_and_escaped_names_do_not_hide_installed_games(tmp_path):
    home, root = steam_home(tmp_path)
    manifest(root).write_text('// app\n"AppState" { "appid" "10" "name" "An \\"example\\"" }')
    assert snapshot(home)["installed"] == ["10"]
    assert snapshot(home)["complete"] is True
