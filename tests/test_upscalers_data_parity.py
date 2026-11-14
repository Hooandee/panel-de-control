"""Shared data contract with the Windows port (windows/tests/PanelDeControl.Core.Tests/Upscalers).

`shared/fixtures/upscalers/data_parity.json` records how the Linux backend reads the neutral build catalog and the
game recipes: every loaded value, every recipe match per system, engine and architecture, and the error code for a
set of broken inputs. The C# loaders must give the same answers. Rewrite it after a data change with
`PYTHONPATH=py_modules python tests/test_upscalers_data_parity.py --write`.
"""

import copy
import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from upscalers import catalog, recipe_catalog

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "shared" / "fixtures" / "upscalers" / "data_parity.json"
PLATFORMS = ("linux", "windows", "darwin")
ARCHES = ("x86_64", "aarch64")
ENGINES = tuple(sorted(recipe_catalog._ENGINES))

CATALOG_CASES = [
    {"id": "schema-version", "op": "set", "path": ["schema_version"], "value": 2},
    {"id": "missing-ffx-loader", "op": "delete", "path": ["ffx_loader"]},
    {"id": "unknown-top-level-field", "op": "set", "path": ["extra"], "value": 1},
    {"id": "bad-sha256", "op": "set", "path": ["assets", 0, "sha256"], "value": "XYZ"},
    {"id": "zero-size", "op": "set", "path": ["assets", 0, "size"], "value": 0},
    {"id": "bool-generation", "op": "set", "path": ["assets", 0, "generation"], "value": True},
    {"id": "null-member", "op": "set", "path": ["assets", 0, "member"], "value": None},
    {"id": "empty-url", "op": "set", "path": ["assets", 0, "urls"], "value": [""]},
    {"id": "image-as-text", "op": "set", "path": ["builds", 0, "image"], "value": "3"},
    {"id": "channel-as-number", "op": "set", "path": ["builds", 0, "channel"], "value": 5},
    {"id": "null-injector", "op": "set", "path": ["builds", 0, "injector"], "value": None},
    {"id": "empty-model-id", "op": "set", "path": ["builds", 1, "models", 0, "id"], "value": ""},
    {"id": "models-not-list", "op": "set", "path": ["builds", 0, "models"], "value": {}},
    {"id": "build-missing-asset", "op": "set", "path": ["builds", 0, "archive"], "value": "no-such-asset"},
    {"id": "duplicate-build", "op": "copy", "path": ["builds", 1, "id"], "from": ["builds", 0, "id"]},
    {"id": "preferred-missing-build", "op": "set", "path": ["preferred", "rdna2"], "value": "no-such-build"},
    {"id": "ratio-as-bool", "op": "set", "path": ["quality_ratios", "native"], "value": True},
    {"id": "archive-role-missing", "op": "delete", "path": ["archives", "lsfg"]},
    {"id": "duplicate-key", "raw": "{\"schema_version\": 1, \"schema_version\": 1}"},
    {"id": "not-json", "raw": "{\"schema_version\": 1,"},
]

RECIPE_CASES = [
    {"id": "missing-windows-block", "file": "games/1462040.json", "op": "delete", "path": ["windows"]},
    {"id": "unknown-status", "file": "games/1462040.json", "op": "set", "path": ["windows", "status"], "value": "works"},
    {"id": "unknown-block-with-fields", "file": "games/292030.json", "op": "set", "path": ["windows", "exe"], "value": "x.exe"},
    {"id": "proton-verb-on-windows", "file": "games/1462040.json", "op": "set", "path": ["windows", "dependencies"],
     "value": ["luma-ff7", "vcrun2022"]},
    {"id": "windows-runtime-on-linux", "file": "games/1462040.json", "op": "set", "path": ["linux", "dependencies"],
     "value": ["luma-ff7", "vcrun2022", "msvcrt40", "vc-redist-x64"]},
    {"id": "exe-escapes-folder", "file": "games/1462040.json", "op": "set", "path": ["windows", "exe"], "value": "../x.exe"},
    {"id": "shell-in-argument", "file": "games/1462040.json", "op": "set", "path": ["windows", "args"], "value": ["-dx11;echo"]},
    {"id": "unknown-engine", "file": "games/1462040.json", "op": "set", "path": ["windows", "conditions", "engine"], "value": ["warp"]},
    {"id": "zero-revision", "file": "games/1462040.json", "op": "set", "path": ["windows", "revision"], "value": 0},
    {"id": "bad-effective-api", "file": "games/1462040.json", "op": "set", "path": ["windows", "effective_api"], "value": "d3d9"},
    {"id": "missing-dependency", "file": "games/1462040.json", "op": "set", "path": ["windows", "dependencies"], "value": ["nope"]},
    {"id": "runtime-page-host", "file": "dependencies.json", "op": "set", "path": ["vc-redist-x64", "page_url"],
     "value": "https://example.com/vc_redist"},
    {"id": "runtime-version", "file": "dependencies.json", "op": "set", "path": ["vc-redist-x64", "min_version"], "value": "latest"},
    {"id": "runtime-component", "file": "dependencies.json", "op": "set", "path": ["vc-redist-x64", "component"], "value": "vc14_arm64"},
    {"id": "dependency-cycle", "file": "dependencies.json", "op": "set", "path": ["luma-ff7", "requires"], "value": ["luma-ff7"]},
    {"id": "asset-off-github", "file": "assets.json", "op": "set", "path": ["luma-ff7-800", "url"], "value": "https://example.com/a.zip"},
    {"id": "schema-version", "file": "catalog.json", "op": "set", "path": ["schema_version"], "value": 1},
    {"id": "game-file-name", "file": "games/ff7.json", "op": "create", "value": {}},
]


def _apply(document, case):
    if case["op"] == "create":
        return copy.deepcopy(case["value"])
    document = copy.deepcopy(document)
    *parents, last = case["path"]
    target = document
    for key in parents:
        target = target[key]
    if case["op"] == "delete":
        del target[last]
    elif case["op"] == "copy":
        source = document
        for key in case["from"]:
            source = source[key]
        target[last] = source
    else:
        target[last] = case["value"]
    return document


def _error(action) -> str | None:
    try:
        action()
    except (catalog.CatalogError, recipe_catalog.CatalogError) as error:
        return str(error)
    return None


def _catalog_error(case) -> str | None:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "catalog.json"
        if "raw" in case:
            path.write_text(case["raw"], encoding="utf-8")
        else:
            path.write_text(json.dumps(_apply(json.loads(catalog.CATALOG_PATH.read_text()), case)), encoding="utf-8")

        def load():
            try:
                return catalog._parse(catalog._read(path))
            except json.JSONDecodeError:
                raise catalog.CatalogError("invalid_json") from None
        return _error(load)


def _recipe_error(case) -> str | None:
    with tempfile.TemporaryDirectory() as folder:
        destination = Path(folder) / "recipes"
        shutil.copytree(recipe_catalog.CATALOG_PATH, destination)
        target = destination / case["file"]
        current = json.loads(target.read_text()) if target.exists() else None
        target.write_text(json.dumps(_apply(current, case)), encoding="utf-8")
        return _error(lambda: recipe_catalog.load(destination))


def _build(build: catalog.Build) -> dict:
    data = asdict(build)
    data["models"] = [[model, overrides] for model, overrides in build.models]
    return data


def _dependency(dependency: recipe_catalog.DependencySpec) -> dict:
    return asdict(dependency)


def _recipe(loaded: recipe_catalog.Catalog, recipe: recipe_catalog.GameRecipe) -> dict:
    data = asdict(recipe)
    data["game_settings"] = [list(pair) for pair in recipe.game_settings]
    data["ordered_dependencies"] = [d.id for d in loaded.dependency_order(recipe.dependencies, recipe.platform)]
    return data


def snapshot() -> dict:
    loaded = recipe_catalog.load()
    matches = {}
    for appid in sorted(loaded.games):
        for engine in ENGINES:
            for platform in PLATFORMS:
                for arch in ARCHES:
                    recipe = loaded.match(appid, engine, platform, arch)
                    if recipe is not None:
                        matches[f"{appid}|{engine}|{platform}|{arch}"] = _recipe(loaded, recipe)
    document = {
        "schema_version": 1,
        "catalog": {
            "archives": {"optiscaler": catalog.OPTISCALER_ARCHIVE, "optiscaler_beta": catalog.OPTISCALER_BETA,
                         "lsfg": catalog.LSFG_ARCHIVE, "helixsr": catalog.HELIXSR_ARCHIVE,
                         "optipatcher": catalog.OPTIPATCHER},
            "amd": list(catalog.AMD), "every_gpu": list(catalog.EVERY_GPU),
            "preferred": catalog.PREFERRED, "quality_ratios": catalog.QUALITY_RATIOS,
            "easy_modes": catalog.EASY_MODES, "sharpness": catalog.SHARPNESS,
            "proxies": list(catalog.PROXIES), "base_ini": catalog.BASE_INI, "ffx_loader": catalog.FFX_LOADER,
            "assets": [asdict(asset) for asset in catalog.ASSETS.values()],
            "builds": [_build(build) for build in catalog.BUILDS.values()],
        },
        "recipes": {
            "schema_version": loaded.schema_version, "catalog_version": loaded.catalog_version,
            "assets": {key: asdict(asset) for key, asset in loaded.assets.items()},
            "dependencies": {key: _dependency(dep) for key, dep in loaded.dependencies.items()},
            "games": {appid: {"name": game.name, "statuses": game.statuses} for appid, game in sorted(loaded.games.items())},
            "platforms": list(PLATFORMS), "arches": list(ARCHES), "engines": list(ENGINES),
            "matches": matches,
        },
        "invalid_catalog": [{**case, "error": _catalog_error(case)} for case in CATALOG_CASES],
        "invalid_recipes": [{**case, "error": _recipe_error(case)} for case in RECIPE_CASES],
    }
    return json.loads(json.dumps(document))


def test_fixture_matches_the_linux_backend():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == snapshot()


def test_every_broken_input_is_rejected():
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert all(case["error"] for case in document["invalid_catalog"] + document["invalid_recipes"])


if __name__ == "__main__" and "--write" in sys.argv:
    FIXTURE.write_text(json.dumps(snapshot(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
