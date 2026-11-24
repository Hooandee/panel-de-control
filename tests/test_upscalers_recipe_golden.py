"""Linux recipe resolution must not drift: every hand-curated game resolves to the values recorded here."""

import json
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path


from upscalers import recipe_catalog, recipes

FIXTURE = Path(__file__).with_name("fixtures") / "recipe_golden.json"
ENGINES = ("optiscaler", "dll")
PROVENANCE = ("source", "catalog_revision", "catalog_version")
EXTRA_APPIDS = ("1245620", "870780", "2054970", "2246340", "1446780", "990080", "1091500", "2124490", "1182900",
                "548430", "230410", "1174180", "2322010", "292030", "1", "999999999")
VARIANTS = ("", "plain", "re")


def _plain(recipe):
    if recipe is None:
        return None
    data = asdict(recipe)
    for key in PROVENANCE:
        data.pop(key)
    return json.loads(json.dumps(data))


def _root(base: Path, variant: str) -> Path | None:
    if not variant:
        return None
    root = base / variant
    root.mkdir(exist_ok=True)
    if variant == "re":
        (root / recipes.RE_ENGINE_MARKER).write_bytes(b"")
    return root


def _resolve(appid: str, engine: str, root: Path | None):
    recipe = recipes.recipe_for(appid, engine=engine, platform="linux", arch="x86_64")
    if root is not None:
        recipe = recipes.with_engine(recipe, appid, root)
    return _plain(recipe)


def snapshot(base: Path) -> dict:
    appids = sorted({*recipe_catalog.bundled().games, *EXTRA_APPIDS, *recipes.RECIPES}, key=int)
    return {f"{appid}|{engine}|{variant}": _resolve(appid, engine, _root(base, variant))
            for appid in appids for engine in ENGINES for variant in VARIANTS}


def test_every_golden_game_resolves_unchanged(tmp_path):
    golden = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for key, expected in golden.items():
        appid, engine, variant = key.split("|")
        assert _resolve(appid, engine, _root(tmp_path, variant)) == expected, key


def test_golden_covers_the_hand_curated_games():
    appids = {key.split("|")[0] for key in json.loads(FIXTURE.read_text(encoding="utf-8"))}
    assert set(EXTRA_APPIDS) <= appids


if __name__ == "__main__" and "--write" in sys.argv:
    with tempfile.TemporaryDirectory() as directory:
        FIXTURE.write_text(json.dumps(snapshot(Path(directory)), indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                           encoding="utf-8")
