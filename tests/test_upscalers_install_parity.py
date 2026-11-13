"""Game-folder install, removal and recovery cases shared with the Windows port.

`shared/fixtures/upscalers/install_parity.json` records, for each scenario below, the game folder (manifest and
backups included) after every step the Linux backend takes, plus what `ini.apply` and `_archive_sources` answer.
windows/tests/PanelDeControl.Core.Tests/Upscalers must leave the same folders. Rewrite it after a change with
`PYTHONPATH=py_modules python tests/test_upscalers_install_parity.py --write`.
"""

import json
import sys
import tempfile
from itertools import product
from pathlib import Path
from unittest import mock

from upscalers import catalog, games, ini, service
from upscalers.service import UpscalerService

FIXTURE = Path(__file__).parents[1] / "shared" / "fixtures" / "upscalers" / "install_parity.json"
INI = "[Upscalers]\nDx12Upscaler=auto\n\n[Menu]\nOverlayMenu=auto\n"
SOURCES = {
    "OptiScaler.dll": "optiscaler proxy",
    "OptiScaler/fakenvapi.dll": "fakenvapi",
    "OptiScaler/D3D12_Optiscaler/D3D12Core.dll": "agility",
    "amd_fidelityfx_upscaler_dx12.dll": "fsr4 int8 upscaler",
    "amd_fidelityfx_loader_dx12.dll": "fsr4 loader",
}
GAME = {
    "Game.exe": "game exe",
    "amd_fidelityfx_upscaler_dx12.dll": "game fsr 3.1",
    "OptiScaler/readme.txt": "a folder the game already had",
}
OPTISCALER = {"dxgi.dll": "OptiScaler.dll", "OptiScaler/fakenvapi.dll": "OptiScaler/fakenvapi.dll",
              "OptiScaler/D3D12_Optiscaler/D3D12Core.dll": "OptiScaler/D3D12_Optiscaler/D3D12Core.dll",
              "amd_fidelityfx_upscaler_dx12.dll": "amd_fidelityfx_upscaler_dx12.dll"}
DLL = {"amd_fidelityfx_upscaler_dx12.dll": "amd_fidelityfx_upscaler_dx12.dll",
       "amd_fidelityfx_loader_dx12.dll": "amd_fidelityfx_loader_dx12.dll"}
SCENARIOS = {
    "install-remove": {"game": GAME, "steps": [
        {"op": "apply", "files": OPTISCALER, "ini": INI}, {"op": "remove"}]},
    "existing-ini-and-log": {"game": {**GAME, "OptiScaler.ini": "user ini", "OptiScaler.log": "old log"}, "steps": [
        {"op": "apply", "files": OPTISCALER, "ini": INI}, {"op": "write", "path": "OptiScaler.log", "text": "new log"},
        {"op": "remove"}]},
    "generated-log-removed": {"game": GAME, "steps": [
        {"op": "apply", "files": OPTISCALER, "ini": INI}, {"op": "write", "path": "OptiScaler.log", "text": "run log"},
        {"op": "remove"}]},
    "game-replaced-a-file": {"game": GAME, "steps": [
        {"op": "apply", "files": OPTISCALER, "ini": INI},
        {"op": "write", "path": "amd_fidelityfx_upscaler_dx12.dll", "text": "patched by a game update"},
        {"op": "remove"}, {"op": "recover"}]},
    "user-edited-ini": {"game": GAME, "steps": [
        {"op": "apply", "files": OPTISCALER, "ini": INI}, {"op": "write", "path": "OptiScaler.ini", "text": "edited"},
        {"op": "remove"}]},
    "file-deleted-meanwhile": {"game": GAME, "steps": [
        {"op": "apply", "files": OPTISCALER, "ini": INI}, {"op": "delete", "path": "dxgi.dll"}, {"op": "remove"}]},
    "interrupted-copy": {"game": GAME, "steps": [
        {"op": "apply", "files": OPTISCALER, "ini": INI, "fail_at": 3}]},
    "interrupted-first-copy": {"game": GAME, "steps": [
        {"op": "apply", "files": OPTISCALER, "ini": INI, "fail_at": 1}]},
    "dll-mode": {"game": {**GAME, "OptiScaler.log": "someone else's log"}, "steps": [
        {"op": "apply", "files": DLL, "ini": None}, {"op": "remove"}]},
    "reinstall": {"game": GAME, "steps": [
        {"op": "apply", "files": OPTISCALER, "ini": INI}, {"op": "remove"},
        {"op": "apply", "files": DLL, "ini": None}, {"op": "remove"}]},
    "orphan-with-manifest": {"game": GAME, "steps": [
        {"op": "apply", "files": OPTISCALER, "ini": INI}, {"op": "recover"}]},
    "orphan-backups-only": {"game": GAME, "steps": [
        {"op": "apply", "files": OPTISCALER, "ini": INI}, {"op": "delete", "path": ".pdc-upscaler/manifest.json"},
        {"op": "recover"}]},
    "remove-without-manifest": {"game": GAME, "steps": [{"op": "remove"}, {"op": "recover"}]},
    "stale-backup-wins": {"game": {**GAME, ".pdc-upscaler/backup/amd_fidelityfx_upscaler_dx12.dll": "true original"},
                          "steps": [{"op": "apply", "files": OPTISCALER, "ini": INI}, {"op": "remove"}]},
}
INI_CASES = {
    "set-existing": (INI, {"Upscalers.Dx12Upscaler": "fsr31"}),
    "append-key": (INI, {"Upscalers.Dx11Upscaler": "fsr22"}),
    "append-section": (INI, {"FrameGen.Enabled": "true", "FrameGen.FGInput": "fsrfg"}),
    "crlf": (INI.replace("\n", "\r\n"), {"Menu.OverlayMenu": "false", "Plugins.LoadAsiPlugins": "true"}),
    "no-final-newline": ("[Menu]\nOverlayMenu=auto", {"Menu.Scale": "1.0", "Log.LogLevel": "2"}),
    "spaced-key": ("[A]\n  Key = 1\nOther=2\n[B]\nKey=3\n", {"A.Key": "9", "B.New": "x"}),
    "empty": ("", {"A.B": "c"}),
    "section-at-end-no-newline": ("[A]\nX=1\n[B]", {"B.Y": "2", "A.Z": "3"}),
    "comments-kept": ("; top\n[A]\n; help\nX=1 ; trailing\n", {"A.X": "2"}),
}
ARCHIVES = {
    "release-0.9": (9, ["OptiScaler.dll", "OptiScaler.ini", "setup_linux.sh", "setup_windows.bat", "!README.txt",
                        ".hidden", "fakenvapi.ini", "D3D12_Optiscaler/D3D12Core.dll", "D3D12_Optiscaler/x/y.dll",
                        "D3D12_Optiscaler/install.bat", "Licenses/MIT.txt", "OptiScaler/ignored.dll"]),
    "nightly-10": (10, ["OptiScaler.dll", "OptiScaler.ini", "OptiScaler/fakenvapi.dll", "OptiScaler/Run.BAT",
                        "OptiScaler/sub/a.dll", "D3D12_Optiscaler/D3D12Core.dll", "readme.md"]),
}

PANEL_GPUS = ("rdna35", "rdna2", "intel", "nvidia")
PANEL_INPUTS = {"fsr31": {"fsr31": ["amd_fidelityfx_dx12.dll"]}, "dlss": {"dlss": ["nvngx_dlss.dll"]},
                "fsrfg": {"fsr31": ["amd_fidelityfx_dx12.dll"], "fsrfg": ["amd_fidelityfx_dx12.dll"]}}
PANEL_CHOICES = ({}, {"quality": "performance", "sharpness": "off"}, {"quality": "native", "sharpness": "high"},
                 {"quality": "bogus", "sharpness": "soft", "fg": "on"}, {"model": "lite"}, {"model": "full", "fg": "on"})


class PanelRecipe:
    """The recipe attributes `panel_ini` reads."""
    def __init__(self, values: dict, optipatcher: bool):
        self.ini = values
        self.optipatcher = optipatcher


PANEL_RECIPES = {"none": None, "ini": PanelRecipe({"Menu.OverlayMenu": "false", "Upscalers.Dx12Upscaler": "xess"}, False),
                 "optipatcher": PanelRecipe({}, True)}


def _panel() -> dict:
    """OptiScaler.ini keys Panel owns for every OptiScaler build, GPU, game inputs, recipe and choice: ordered pairs."""
    cases = {}
    builds = [build for build in catalog.BUILDS.values() if build.engine == "optiscaler"]
    for build, gpu, inputs, recipe, index in product(builds, PANEL_GPUS, PANEL_INPUTS, PANEL_RECIPES, range(len(PANEL_CHOICES))):
        effective = catalog.for_game(build, PANEL_INPUTS[inputs], gpu)
        generation = catalog.ASSETS[effective.archive].generation
        plan = catalog.fg_plan(gpu, PANEL_INPUTS[inputs], None, generation, ["d3d12"], 2, None)
        values = service.panel_ini(effective, PANEL_RECIPES[recipe], PANEL_CHOICES[index], plan)
        cases[f"{build.id}|{gpu}|{inputs}|{recipe}|{index}"] = [[key, value] for key, value in values.items()]
    values, index_of, keys = [], {}, {}
    for key, value in cases.items():
        text = json.dumps(value)
        if text not in index_of:
            index_of[text] = len(values)
            values.append(value)
        keys[key] = index_of[text]
    return {"values": values, "cases": keys}


def _tree(folder: Path) -> dict:
    result = {}
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder).as_posix()
        if path.is_dir():
            if not any(path.iterdir()):
                result[relative + "/"] = None
            continue
        text = path.read_text(encoding="utf-8")
        result[relative] = json.loads(text) if path.name == "manifest.json" else text
    return result


def _write(folder: Path, files: dict) -> None:
    for relative, text in files.items():
        (folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (folder / relative).write_text(text, encoding="utf-8")


def _orphans() -> UpscalerService:
    """Only what `_recover_orphan` reads: no install claims the folder, and removal is the bare file step."""
    owner = UpscalerService.__new__(UpscalerService)
    owner.state = {"games": {}}
    owner.logger = None
    owner._remove = UpscalerService._remove_files
    return owner


def _run(scenario: dict) -> list[dict]:
    with tempfile.TemporaryDirectory() as temp:
        game, cache = Path(temp, "game"), Path(temp, "cache")
        game.mkdir()
        _write(game, scenario["game"])
        _write(cache, SOURCES)
        steps = []
        for step in scenario["steps"]:
            outcome: dict = {}
            if step["op"] == "apply":
                sources = {name: cache / source for name, source in step["files"].items()}
                real_copy, calls = service.shutil.copyfile, []

                def copy(source, destination, step=step):
                    calls.append(source)
                    if len(calls) == step.get("fail_at"):
                        raise OSError("disk full")
                    return real_copy(source, destination)

                try:
                    with mock.patch.object(service.shutil, "copyfile", copy):
                        outcome["result"] = UpscalerService._apply_files(_orphans(), game, sources, step["ini"])
                except OSError as error:
                    outcome["error"] = str(error)
            elif step["op"] == "remove":
                outcome["kept"] = UpscalerService._remove_files(game)
            elif step["op"] == "recover":
                _orphans()._recover_orphan(game)
            elif step["op"] == "write":
                (game / step["path"]).write_text(step["text"], encoding="utf-8")
            elif step["op"] == "delete":
                (game / step["path"]).unlink()
            outcome["tree"] = _tree(game)
            steps.append(outcome)
        return steps


def _archive(generation: int, files: list[str]) -> list[str]:
    with tempfile.TemporaryDirectory() as temp:
        _write(Path(temp), {name: name for name in files})
        return sorted(service._archive_sources(Path(temp), generation))


def snapshot() -> dict:
    document = {
        "schema_version": 1,
        "manifest_dir": games.MANIFEST_DIR,
        "sources": SOURCES,
        "scenarios": {name: {**scenario, "results": _run(scenario)} for name, scenario in SCENARIOS.items()},
        "ini": {name: {"text": text, "overrides": overrides, "result": ini.apply(text, overrides),
                       "reads": {key: ini.read(ini.apply(text, overrides), key) for key in overrides}}
                for name, (text, overrides) in INI_CASES.items()},
        "panel": {"inputs": PANEL_INPUTS, "choices": list(PANEL_CHOICES),
                  "recipes": {key: {"ini": value.ini, "optipatcher": value.optipatcher} if value else None
                              for key, value in PANEL_RECIPES.items()},
                  **_panel()},
        "archives": {name: {"generation": generation, "files": files, "sources": _archive(generation, files)}
                     for name, (generation, files) in ARCHIVES.items()},
    }
    return json.loads(json.dumps(document))


def test_fixture_matches_the_linux_backend():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == snapshot()


if __name__ == "__main__" and "--write" in sys.argv:
    FIXTURE.write_text(json.dumps(snapshot(), separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
