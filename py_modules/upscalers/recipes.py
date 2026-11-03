"""What a particular game needs besides OptiScaler, so nobody has to research it.

Hand-written entries are checked against the game's files and a real install on a handheld.
`recipes_wiki.json` is generated from the OptiScaler wiki's compatibility table and only carries
facts Panel can apply (proxy name, launch arguments) or must warn about (REFramework, a copied
nvngx_dlss.dll, anti-cheat, games that do not work). Hand-written entries win. Panel applies a
recipe on install and undoes exactly what it added.
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

WIKI_FILE = Path(__file__).with_name("recipes_wiki.json")
NEEDS = ("reframework", "nvngx_dlss", "anti_cheat_off")


@dataclass(frozen=True)
class Recipe:
    appid: str
    exe: str | None = None
    args: tuple[str, ...] = ()
    files: dict[str, str] = field(default_factory=dict)
    native_dlls: tuple[str, ...] = ()
    ini: dict[str, str] = field(default_factory=dict)
    fg: dict[str, str] | None = None
    fg_note: str | None = None
    proxy: str | None = None
    needs: tuple[str, ...] = ()
    broken: bool = False
    optipatcher: bool = False
    source: str = "panel"


RECIPES: dict[str, Recipe] = {
    recipe.appid: recipe
    for recipe in (
        # REDlauncher waits for a click under Proton; DX12 is the build that ships the upscalers.
        # graphics.xml: FSR Frame Generation is disabled while Reflex is on.
        Recipe("292030", exe="bin/x64_dx12/witcher3.exe", args=("--launcher-skip", "-dx12"), fg_note="reflexOff"),
        # RE Engine exposes its upscaler to OptiScaler only through REFramework.
        Recipe("2054970", files={"dinput8.dll": "reframework-nightly"}, native_dlls=("dinput8",)),
    )
}


def _wiki(path: Path = WIKI_FILE) -> dict[str, Recipe]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    source = str(data.get("source") or "optiscaler-wiki")
    loaded = {}
    for appid, entry in (data.get("recipes") or {}).items():
        if not str(appid).isdecimal() or not isinstance(entry, dict):
            continue
        recipe = from_facts(str(appid), entry, source)
        if recipe:
            loaded[str(appid)] = recipe
    return loaded


def from_facts(appid: str, entry: dict, source: str) -> Recipe | None:
    """A recipe from the wiki's facts, or None when they change nothing and warn about nothing."""
    recipe = Recipe(
        appid,
        args=tuple(a for a in entry.get("args", ()) if a == "-dx12"),
        proxy=entry.get("proxy") if isinstance(entry.get("proxy"), str) else None,
        needs=tuple(n for n in entry.get("needs", ()) if n in NEEDS),
        broken=entry.get("status") == "broken",
        optipatcher=bool(entry.get("optipatcher")),
        source=source,
    )
    return recipe if recipe.args or recipe.proxy or recipe.needs or recipe.broken or recipe.optipatcher else None


WIKI = _wiki()


def applies(recipe: Recipe | None) -> bool:
    """Whether installing changes anything because of the recipe."""
    return bool(recipe and (recipe.exe or recipe.args or recipe.files or recipe.native_dlls or recipe.ini
                            or recipe.fg or recipe.proxy or recipe.optipatcher))


def recipe_for(appid: str) -> Recipe | None:
    return RECIPES.get(str(appid)) or WIKI.get(str(appid))


# Every RE Engine game ships its packs as re_chunk_000.pak in the game root.
RE_ENGINE_MARKER = "re_chunk_000.pak"
REFRAMEWORK = {"dinput8.dll": "reframework-nightly"}


def with_engine(recipe: Recipe | None, appid: str, root: Path) -> Recipe | None:
    """Capcom's RE Engine only shows its upscaler to OptiScaler through REFramework (OptiScaler wiki)."""
    if not (root / RE_ENGINE_MARKER).is_file():
        return recipe
    base = recipe or Recipe(str(appid))
    if base.files:
        return base
    return replace(base, files=dict(REFRAMEWORK), native_dlls=(*base.native_dlls, "dinput8"),
                   needs=tuple(n for n in base.needs if n != "reframework"))
