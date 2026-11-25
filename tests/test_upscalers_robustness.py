"""Escaladores degrades instead of failing whole: a failed HelixSR install is undone, a broken catalog or recipe file costs only itself."""

import importlib.util
import json
import logging
import shutil
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

for _name in ("pwd", "fcntl"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from upscalers import auto_recipes, catalog, game_config, helixsr, recipe_catalog  # noqa: E402
from upscalers.service import UpscalerError, UpscalerService  # noqa: E402

ROOT = Path(__file__).parents[1]
LIBRARY = "amd_fidelityfx_dx12.dll"
BACKUP = "amd_fidelityfx_dx12.original.dll"


class SwappingHelix:
    """A bridge that swaps the game's DLL and then fails; `remove` works or fails as the test says."""

    def __init__(self, folder: Path, remove_works: bool):
        self.folder = folder
        self.remove_works = remove_works
        self.calls = []
        self.release = Path("HelixSR-3.2.0")

    def ready(self):
        return True

    def digest(self):
        return None

    def install(self, game):
        self.calls.append("install")
        shutil.move(self.folder / LIBRARY, self.folder / BACKUP)
        (self.folder / LIBRARY).write_bytes(b"HLX-FSR-4 drop-in")
        (self.folder / "helixsr-install.json").write_text(json.dumps({"files": [LIBRARY]}))
        raise helixsr.HelixError("helixsr_failed", "died after swapping")

    def remove(self, game):
        self.calls.append("remove")
        if not self.remove_works:
            raise helixsr.HelixError("helixsr_failed", "remove failed too")
        (self.folder / LIBRARY).unlink()
        shutil.move(self.folder / BACKUP, self.folder / LIBRARY)
        (self.folder / "helixsr-install.json").unlink()
        return {}


@pytest.mark.parametrize("remove_works", [True, False])
def test_a_helix_install_that_fails_after_swapping_puts_the_games_dll_back(tmp_path, monkeypatch, remove_works):
    folder = tmp_path / "game"
    folder.mkdir()
    (folder / LIBRARY).write_bytes(b"game fsr 3.1")
    pinned = SimpleNamespace(id="helix", sha256="0" * 64)
    monkeypatch.setattr(catalog, "ASSETS", {"helix": pinned})
    service = UpscalerService.__new__(UpscalerService)
    service.logger = None
    service.helix = SwappingHelix(folder, remove_works)
    service.latest = SimpleNamespace(resolve=lambda asset: None)
    installed = SimpleNamespace(root=tmp_path, launcher=None)
    service._guard = lambda appid, confirm: (installed, {"inputs": ["fsr31"], "foreign": False, "exe": "g.exe"}, folder)
    service._game_state = lambda appid: {"install": None}
    service._replace = lambda entry, installed: None
    service._update_job = lambda **fields: None
    build = SimpleNamespace(way="fsr", archive="helix", id="hlx-fsr4")

    with pytest.raises(UpscalerError) as failure:
        service._install_helix("1", build, {})

    assert (failure.value.code, failure.value.detail) == ("helixsr_failed", "died after swapping")
    assert (folder / LIBRARY).read_bytes() == b"game fsr 3.1"
    assert not (folder / BACKUP).exists() and not (folder / "helixsr-install.json").exists()
    assert service.helix.calls == ["install", "remove"]


def _load_catalog_module(tmp_path: Path, shared: str | None):
    package = tmp_path / "py_modules" / "upscalers"
    package.mkdir(parents=True)
    shutil.copy(ROOT / "py_modules" / "upscalers" / "catalog.py", package / "catalog.py")
    if shared is not None:
        (tmp_path / "shared" / "upscalers").mkdir(parents=True)
        (tmp_path / "shared" / "upscalers" / "catalog.json").write_text(shared)
    spec = importlib.util.spec_from_file_location("catalog_isolated", package / "catalog.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("shared", [None, "{ not json", "[]", '{"schema_version": 1}'])
def test_a_missing_or_corrupt_catalog_leaves_an_empty_one_and_logs_once(tmp_path, caplog, shared):
    with caplog.at_level(logging.ERROR):
        module = _load_catalog_module(tmp_path, shared)

    assert module.BUILDS == {} and module.ASSETS == {}
    assert module.describe("rdna3") == [] and module.anr_build("rdna3") is None
    assert module.ERROR
    assert len([record for record in caplog.records if "catalog unavailable" in record.getMessage()]) == 1


def test_the_shipped_catalog_has_no_error():
    assert catalog.ERROR is None and catalog.BUILDS


def test_the_overview_says_when_the_catalog_is_unavailable(monkeypatch):
    monkeypatch.setattr(catalog, "BUILDS", {})
    monkeypatch.setattr(catalog, "ASSETS", {})
    monkeypatch.setattr(catalog, "ERROR", "invalid_fields")
    service = UpscalerService.__new__(UpscalerService)
    service.state = {"games": {}}
    service.gpu, service.device, service.drm = "rdna3", "", None
    service.cache = SimpleNamespace(ready=lambda asset: False)
    service.helix = SimpleNamespace(ready=lambda: False)
    service.job = lambda: None
    service._engine_summaries = lambda: {}

    with mock.patch("upscalers.service.panel_resolution", return_value=None):
        overview = service.overview()

    assert (overview["builds"], overview["catalog_error"]) == ([], "invalid_fields")


def _recipe_files(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / "game-recipes", tmp_path / "recipes")
    return tmp_path / "recipes"


@pytest.mark.parametrize("content", ["{ not json", '{"name": "Broken"}'])
def test_a_broken_game_file_is_skipped_and_the_other_recipes_survive(tmp_path, caplog, content):
    folder = _recipe_files(tmp_path)
    broken = sorted((folder / "games").glob("*.json"))[0]
    whole = recipe_catalog.load(folder)
    broken.write_text(content)

    with caplog.at_level(logging.WARNING):
        partial = recipe_catalog.load(folder, skip_broken_games=True)

    assert broken.stem not in partial.games and len(partial.games) == len(whole.games) - 1
    assert any(broken.name in record.getMessage() or broken.stem in record.getMessage() for record in caplog.records)
    with pytest.raises(recipe_catalog.CatalogError):
        recipe_catalog.load(folder)


def test_the_bundled_catalog_keeps_every_recipe_when_one_game_file_is_broken(tmp_path, monkeypatch):
    folder = _recipe_files(tmp_path)
    (folder / "games" / "999999.json").write_text("{ not json")
    real = recipe_catalog.load
    monkeypatch.setattr(recipe_catalog, "load", lambda **options: real(folder, **options))
    recipe_catalog.bundled.cache_clear()
    try:
        bundled = recipe_catalog.bundled()
    finally:
        recipe_catalog.bundled.cache_clear()

    assert "999999" not in bundled.games and len(bundled.games) == len(real().games)


def test_a_reinstall_that_kept_the_earlier_edit_remembers_the_users_original(tmp_path, monkeypatch):
    monkeypatch.setattr(game_config.ownership, "own_like", lambda folder, paths: None)
    path = tmp_path / "system.xml"
    path.write_text("<API>kSettingAPI_Vulkan</API>")
    entries = (("system.xml", "API", "kSettingAPI_DX12"),)
    first = game_config.apply(tmp_path, entries)
    again = game_config.apply(tmp_path, entries)

    assert [record["state"] for record in again] == ["already"]
    carried = game_config.carry(first, again)

    assert carried[0]["state"] == "set"
    game_config.restore(carried)
    assert path.read_text() == "<API>kSettingAPI_Vulkan</API>"


def test_a_file_that_fails_to_come_out_for_an_io_reason_is_kept(tmp_path):
    (tmp_path / "bad.ini").write_text("changed")
    meta = tmp_path / ".pdc-upscaler"
    meta.mkdir()
    (meta / "manifest.json").write_text(json.dumps({"files": {"bad.ini": "0" * 64}, "backups": [], "dirs": [],
                                                    "configuration": {"bad.ini": {}}}))
    with mock.patch.object(auto_recipes, "restore_configuration", side_effect=PermissionError("denied")):
        assert UpscalerService._remove_files(tmp_path) == ["bad.ini"]
