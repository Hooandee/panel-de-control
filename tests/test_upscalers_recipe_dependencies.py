"""Recipe dependencies and configuration shared with the Windows port.

`shared/fixtures/upscalers/recipe_dependencies.json` records what `upscalers.auto_recipes` answers for the Windows block
of the curated games that need Luma (plan order, assets, where each unpacked file goes) and how it edits and restores a
game's ReShade.ini. windows/tests/PanelDeControl.Core.Tests/Upscalers must answer the same. Rewrite it after a change with
`PYTHONPATH=py_modules python tests/test_upscalers_recipe_dependencies.py --write`.
"""

import json
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

try:
    from upscalers import auto_recipes, recipe_catalog
except ImportError:
    # The package needs Linux modules (pwd, fcntl); these two only need the catalog and the INI editor.
    _PACKAGE = types.ModuleType("upscalers")
    _PACKAGE.__path__ = [str(Path(__file__).parents[1] / "py_modules" / "upscalers")]
    sys.modules["upscalers"] = _PACKAGE
    from upscalers import auto_recipes, recipe_catalog

FIXTURE = Path(__file__).parents[1] / "shared" / "fixtures" / "upscalers" / "recipe_dependencies.json"
GAMES = {"1462040": "Final Fantasy VII Remake", "1687950": "Persona 5 Royal"}
CHANGES = {"ReShade.ini": {"Luma.SRUserType": "2", "OVERLAY.TutorialProgress": "4"}}
BOM = "\ufeff"
EXISTING = {
    "none": None,
    "empty": "",
    "other-sections": "[GENERAL]\nEffectSearchPaths=.\\\n",
    "luma-and-overlay": "[Luma]\nSRUserType=0\nOther=4\n[OVERLAY]\nTutorialProgress=0\nKeyOverlay=36,0,0,0\n",
    "bom-crlf": BOM + ";keep\r\n[Luma]\r\nSRUserType=0\r\nOther=4\r\n[GENERAL]\r\nValue=mine\r\n",
    "already-set": "[Luma]\nSRUserType=2\n[OVERLAY]\nTutorialProgress=4\n",
    "empty-basepath": "[INSTALL]\nBasePath=\n[Luma]\nSRUserType=1\n",
    "basepath": "[INSTALL]\nBasePath=C:\\elsewhere\n",
    "basepath-lowercase": "[install]\nbasepath=elsewhere\n",
    "duplicate-key": "[Luma]\nSRUserType=0\nSRUserType=1\n",
    "duplicate-section": "[Luma]\nOther=1\n[Luma]\nSRUserType=0\n",
    "commented-duplicate": "[Luma]\n;SRUserType=9\nSRUserType=0\n",
}
RESTORES = {
    "put-back": ("[Luma]\nSRUserType=2\nOther=4\n[OVERLAY]\nTutorialProgress=4\n",
                 "[Luma]\nSRUserType=0\nOther=4\n[OVERLAY]\nTutorialProgress=0\n"),
    "no-original-removes-keys": ("[Luma]\nSRUserType=2\nOther=4\n[OVERLAY]\nTutorialProgress=4\nKeyOverlay=36\n", None),
    "user-changed-one": ("[Luma]\nSRUserType=1\n[OVERLAY]\nTutorialProgress=4\n", "[OVERLAY]\nTutorialProgress=0\n"),
    "bom-crlf": (BOM + "[Luma]\r\nSRUserType=2\r\nOther=4\r\n[OVERLAY]\r\nTutorialProgress=4\r\n",
                 "[Luma]\r\nSRUserType=0\r\n"),
    "duplicate-key-in-current": ("[Luma]\nSRUserType=2\nSRUserType=2\n", None),
    "duplicate-section-in-backup": ("[Luma]\nSRUserType=2\n", "[Luma]\nSRUserType=0\n[Luma]\nOther=1\n"),
}


def _plan(appid: str) -> dict:
    catalog = recipe_catalog.bundled()
    selected = catalog.match(appid, "optiscaler", "windows", "amd64")
    assets = auto_recipes.assets(selected)
    with tempfile.TemporaryDirectory() as temp:
        roots, members = {}, {}
        for dependency in auto_recipes.dependencies(selected):
            if dependency.kind != "game_files":
                continue
            root = Path(temp, dependency.asset)
            members[dependency.asset] = sorted(set(dependency.files.values()))
            for member in members[dependency.asset]:
                (root / member).parent.mkdir(parents=True, exist_ok=True)
                (root / member).write_text(member, encoding="utf-8")
            roots[dependency.asset] = root
        base = Path(temp).resolve()
        sources = {destination: Path(*path.relative_to(base).parts[1:]).as_posix()
                   for destination, path in auto_recipes.sources(selected, roots).items()}
    return {
        "dependencies": [{"id": dependency.id, "kind": dependency.kind} for dependency in auto_recipes.dependencies(selected)],
        "assets": [{"id": asset.id, "filename": asset.filename, "sha256": asset.sha256, "size": asset.size, "urls": list(asset.urls)}
                   for asset in assets],
        "members": members,
        "sources": list(sources.items()),
        "configuration": selected.configuration,
    }


def _configured(existing: str | None) -> dict:
    selected = SimpleNamespace(configuration=CHANGES)
    with tempfile.TemporaryDirectory() as temp:
        target, staging = Path(temp, "game"), Path(temp, "staging")
        target.mkdir()
        staging.mkdir()
        if existing is not None:
            (target / "ReShade.ini").write_bytes(existing.encode("utf-8"))
        try:
            result = auto_recipes.configured_sources(selected, target, staging)
        except auto_recipes.RecipeError as error:
            return {"error": error.code}
        return {"text": result["ReShade.ini"].read_bytes().decode("utf-8")}


def _restored(current: str, original: str | None) -> dict:
    with tempfile.TemporaryDirectory() as temp:
        path, backup = Path(temp, "ReShade.ini"), Path(temp, "backup.ini")
        path.write_bytes(current.encode("utf-8"))
        if original is not None:
            backup.write_bytes(original.encode("utf-8"))
        try:
            auto_recipes.restore_configuration(path, backup, CHANGES["ReShade.ini"])
        except auto_recipes.RecipeError as error:
            return {"error": error.code}
        return {"text": path.read_bytes().decode("utf-8")}


def snapshot() -> dict:
    document = {
        "schema_version": 1,
        "games": {appid: {"name": name, **_plan(appid)} for appid, name in GAMES.items()},
        "configured": {name: {"existing": text, **_configured(text)} for name, text in EXISTING.items()},
        "restored": {name: {"current": current, "original": original, **_restored(current, original)}
                     for name, (current, original) in RESTORES.items()},
    }
    return json.loads(json.dumps(document))


def test_fixture_matches_the_linux_backend():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == snapshot()


def test_windows_blocks_keep_their_dependencies_and_configuration():
    for appid in GAMES:
        plan = _plan(appid)
        assert [dependency["kind"] for dependency in plan["dependencies"]] == ["windows_redist", "game_files"]
        assert plan["configuration"] == CHANGES


if __name__ == "__main__" and "--write" in sys.argv:
    FIXTURE.write_text(json.dumps(snapshot(), separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
