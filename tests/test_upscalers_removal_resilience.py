"""A removal that fails on one file still puts the game's originals back, and the game's settings follow the files."""

import json
import sys
import types
from pathlib import Path
from unittest import mock

for _name in ("pwd", "fcntl"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from upscalers import auto_recipes, game_config, games  # noqa: E402
from upscalers.service import UpscalerService  # noqa: E402


def _manifest(target: Path, files: dict, backups: list, **extra) -> None:
    meta = target / games.MANIFEST_DIR
    meta.mkdir(parents=True)
    (meta / "manifest.json").write_text(json.dumps({"files": files, "backups": backups, "dirs": [], **extra}))


def test_a_file_that_fails_to_come_out_is_kept_and_the_backups_still_return(tmp_path):
    (tmp_path / "bad.ini").write_text("changed")
    (tmp_path / "panel.dll").write_text("panel")
    _manifest(tmp_path, {"bad.ini": "0" * 64, "panel.dll": None}, ["dxgi.dll"], configuration={"bad.ini": {}})
    saved = tmp_path / games.MANIFEST_DIR / "backup" / "dxgi.dll"
    saved.parent.mkdir(parents=True)
    saved.write_text("game dxgi")
    with mock.patch.object(auto_recipes, "restore_configuration", side_effect=auto_recipes.RecipeError("bad_ini")):
        kept = UpscalerService._remove_files(tmp_path)
    assert kept == ["bad.ini"]
    assert not (tmp_path / "panel.dll").exists()
    assert (tmp_path / "dxgi.dll").read_text() == "game dxgi"
    assert (tmp_path / games.MANIFEST_DIR / "manifest.json").exists()


def _owner(removal):
    owner = UpscalerService.__new__(UpscalerService)
    owner._remove = removal
    return owner


def test_settings_stay_changed_while_the_files_are_still_installed(tmp_path):
    _manifest(tmp_path, {"x.dll": None}, [])
    install = {"target": str(tmp_path), "game_config": [{"state": "set"}]}
    with mock.patch.object(game_config, "restore") as restore:
        _owner(lambda target: ["x.dll"])._drop(install, tmp_path)
    restore.assert_not_called()


def test_settings_go_back_once_the_files_are_out(tmp_path):
    install = {"target": str(tmp_path), "game_config": [{"state": "set"}]}
    with mock.patch.object(game_config, "restore") as restore:
        _owner(lambda target: [])._drop(install, tmp_path)
    restore.assert_called_once_with(install["game_config"])
