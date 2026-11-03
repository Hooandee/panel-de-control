"""What a particular game needs besides OptiScaler, so nobody has to research it.

Hand-written entries are checked against the game's files and a real install on a handheld.
`recipes_wiki.json` is generated from the whole OptiScaler wiki (`wiki.py`): every listed game with
the community verdict, its inputs, the proxy, -dx12, OptiPatcher, the OptiScaler.ini settings its
page lists and what Panel must warn about (REFramework, a copied nvngx_dlss.dll, anti-cheat, a
third-party mod, games that do not work). Hand-written entries win. Panel applies a recipe on install
and undoes exactly what it added.
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

WIKI_FILE = Path(__file__).with_name("recipes_wiki.json")
NEEDS = ("reframework", "nvngx_dlss", "anti_cheat_off", "luma", "mod")
STATUSES = ("works", "broken", "partial")


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
    # Panel's live-panel key for OptiScaler's menu when the game already uses Insert.
    menu_key: str | None = None
    # The wiki's verdict and what it says without Panel acting on it.
    status: str | None = None
    inputs: tuple[str, ...] = ()
    page: str | None = None
    linux: bool = False
    # OptiScaler.ini `Key=value` pairs from the game's wiki page, resolved against the installed INI on install.
    wiki_settings: dict[str, str] = field(default_factory=dict)
    wiki_suggestions: dict[str, str] = field(default_factory=dict)
    source: str = "panel"


RECIPES: dict[str, Recipe] = {
    recipe.appid: recipe
    for recipe in (
        # REDlauncher waits for a click under Proton; DX12 is the build that ships the upscalers.
        # graphics.xml: FSR Frame Generation is disabled while Reflex is on.
        Recipe("292030", exe="bin/x64_dx12/witcher3.exe", args=("--launcher-skip", "-dx12"), fg_note="reflexOff"),
        # RE Engine exposes its upscaler to OptiScaler only through REFramework.
        Recipe("2054970", files={"dinput8.dll": "reframework-nightly"}, native_dlls=("dinput8",)),
        # Monster Hunter Wilds wiki entry: on AMD/Intel Streamline's own spoof already unlocks DLSS; DXGI spoofing
        # on top crashes it. REFramework comes from the RE Engine rule.
        Recipe("2246340", ini={"Spoofing.Dxgi": "false"}, needs=("reframework",)),
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
        recipe = from_facts(str(appid), entry, source, entry.get("page_facts"))
        if recipe:
            loaded[str(appid)] = recipe
    return loaded


def _pairs(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k)[:64]: str(v)[:64] for k, v in value.items() if str(k).replace("_", "").isalnum()}


def from_facts(appid: str, entry: dict, source: str, page: dict | None = None) -> Recipe | None:
    """A recipe from the wiki's facts for a game, merged with its page when Panel has it."""
    page = page if isinstance(page, dict) else entry.get("page_facts") if isinstance(entry.get("page_facts"), dict) else {}
    proxy = entry.get("proxy") if isinstance(entry.get("proxy"), str) else page.get("proxy")
    status = entry.get("status") if entry.get("status") in STATUSES else None
    recipe = Recipe(
        appid,
        args=tuple(a for a in entry.get("args", ()) if a == "-dx12"),
        proxy=proxy if isinstance(proxy, str) else None,
        needs=tuple(n for n in entry.get("needs", ()) if n in NEEDS),
        broken=status == "broken",
        optipatcher=bool(entry.get("optipatcher")),
        status=status,
        inputs=tuple(str(i)[:12] for i in entry.get("inputs", ()) if isinstance(i, str))[:9],
        page=str(entry["page"])[:120] if isinstance(entry.get("page"), str) else None,
        linux=bool(page.get("linux")),
        wiki_settings=_pairs(page.get("settings")),
        wiki_suggestions=_pairs(page.get("suggestions")),
        source=source,
    )
    return recipe if recipe.status or recipe.args or recipe.proxy or recipe.needs or recipe.optipatcher else None


WIKI = _wiki()


def applies(recipe: Recipe | None) -> bool:
    """Whether installing changes anything because of the recipe."""
    return bool(recipe and (recipe.exe or recipe.args or recipe.files or recipe.native_dlls or recipe.ini
                            or recipe.fg or recipe.proxy or recipe.optipatcher or recipe.wiki_settings))


def combine(hand: Recipe | None, wiki: Recipe | None) -> Recipe | None:
    """A hand-written recipe keeps its own steps and gains what the wiki knows about the game."""
    if hand is None or wiki is None:
        return hand or wiki
    return replace(
        hand,
        proxy=hand.proxy or wiki.proxy,
        args=hand.args or wiki.args,
        needs=tuple(dict.fromkeys((*hand.needs, *wiki.needs))),
        broken=hand.broken or wiki.broken,
        optipatcher=hand.optipatcher or wiki.optipatcher,
        status=wiki.status, inputs=wiki.inputs, page=wiki.page, linux=wiki.linux,
        wiki_settings={k: v for k, v in wiki.wiki_settings.items() if not any(d.endswith(f".{k}") for d in hand.ini)},
        wiki_suggestions=wiki.wiki_suggestions,
    )


def with_wiki(recipe: Recipe | None, live: Recipe | None) -> Recipe | None:
    """The live wiki row replaces the bundled one; the bundled page facts stay until the live page is read."""
    if live is None or recipe is None:
        return live or recipe
    return replace(live, linux=live.linux or recipe.linux, status=live.status or recipe.status,
                   inputs=live.inputs or recipe.inputs, page=live.page or recipe.page,
                   wiki_settings=live.wiki_settings or recipe.wiki_settings,
                   wiki_suggestions=live.wiki_suggestions or recipe.wiki_suggestions,
                   proxy=live.proxy or recipe.proxy)


def recipe_for(appid: str, live: Recipe | None = None) -> Recipe | None:
    return combine(RECIPES.get(str(appid)), with_wiki(WIKI.get(str(appid)), live))


# Every RE Engine game ships its packs as re_chunk_000.pak in the game root.
RE_ENGINE_MARKER = "re_chunk_000.pak"
REFRAMEWORK = {"dinput8.dll": "reframework-nightly"}


def with_engine(recipe: Recipe | None, appid: str, root: Path) -> Recipe | None:
    """Capcom's RE Engine only shows its upscaler to OptiScaler through REFramework (OptiScaler wiki)."""
    if not (root / RE_ENGINE_MARKER).is_file():
        return recipe
    base = recipe or Recipe(str(appid))
    # REFramework opens its own menu with Insert too: OptiScaler's moves to Home (VK 0x24).
    keys = {"ini": {**base.ini, "Menu.ShortcutKey": "0x24"}, "menu_key": "home"}
    if base.files:
        return replace(base, **keys)
    return replace(base, files=dict(REFRAMEWORK), native_dlls=(*base.native_dlls, "dinput8"),
                   needs=tuple(n for n in base.needs if n != "reframework"), **keys)
