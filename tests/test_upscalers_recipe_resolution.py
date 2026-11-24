"""Shared contract with the Windows port: how a game's recipe resolves once the catalog row, the OptiScaler wiki and the
RE Engine rule are composed.

`shared/fixtures/upscalers/recipe_resolution.json` records the resolved recipe per system for a representative set of
games; `windows/tests/PanelDeControl.Core.Tests/Upscalers/RecipeResolverTests.cs` must get the same answers. Rewrite it
after a data change with `PYTHONPATH=py_modules python tests/test_upscalers_recipe_resolution.py --write`.
"""

import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

from upscalers import recipes

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "shared" / "fixtures" / "upscalers" / "recipe_resolution.json"
PLATFORMS = ("linux", "windows")
ARCH = "x86_64"
# (appid, engine, a game folder with re_chunk_000.pak): hand-curated games, Luma games, RE Engine games, wiki-only
# games, a curated game that also has wiki page settings, the DLL engine and a game nobody knows.
CASES = [
    *((appid, "optiscaler", False) for appid in (
        "1245620", "292030", "870780", "2054970", "2246340", "1446780", "990080", "1091500", "2124490", "1182900",
        "548430", "230410", "1174180", "2322010",
        "1462040", "1687950",
        "1196590", "2050650",
        "403640",
        "1938010", "1230530", "251570", "698670",
        "999999999")),
    ("1196590", "optiscaler", True), ("2054970", "optiscaler", True), ("1446780", "optiscaler", True),
    ("999000001", "optiscaler", True), ("1938010", "optiscaler", True),
    ("292030", "dll", False), ("1462040", "dll", False), ("230410", "dll", False),
]
DROPPED = ("fg", "catalog_version")


def _key(platform: str, appid: str, engine: str, marker: bool) -> str:
    return f"{platform}|{appid}|{engine}|{'re' if marker else 'plain'}"


def _resolve(platform: str, appid: str, engine: str, marker: bool, folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    if marker:
        (folder / recipes.RE_ENGINE_MARKER).write_bytes(b"")
    recipe = recipes.with_engine(recipes.recipe_for(appid, engine=engine, platform=platform, arch=ARCH), appid, folder)
    if recipe is None:
        return None
    data = asdict(recipe)
    for key in DROPPED:
        data.pop(key)
    return json.loads(json.dumps(data))


def snapshot(base: Path) -> dict:
    cases = {}
    for index, (appid, engine, marker) in enumerate(CASES):
        for platform in PLATFORMS:
            cases[_key(platform, appid, engine, marker)] = _resolve(platform, appid, engine, marker, base / f"{platform}{index}")
    return {"schema_version": 1, "arch": ARCH, "cases": cases}


def test_fixture_matches_the_linux_backend(tmp_path):
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == snapshot(tmp_path)


def test_fixture_covers_every_kind_of_game():
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    assert cases["windows|230410|optiscaler|plain"]["proxy"] == "winmm.dll"
    assert cases["windows|2322010|optiscaler|plain"]["legacy_ffx_swap"] is False
    assert cases["windows|1446780|optiscaler|re"]["files"] == {"ReShade64.dll": "reframework-nightly"}
    assert cases["windows|999999999|optiscaler|plain"] is None
    assert cases["windows|999000001|optiscaler|re"]["menu_key"] == "home"
    assert cases["windows|1938010|optiscaler|plain"]["source"].startswith("optiscaler-wiki@")


if __name__ == "__main__" and "--write" in sys.argv:
    with tempfile.TemporaryDirectory() as directory:
        FIXTURE.write_text(json.dumps(snapshot(Path(directory)), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
