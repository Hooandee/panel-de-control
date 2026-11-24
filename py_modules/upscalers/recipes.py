"""What a particular game needs besides OptiScaler, so nobody has to research it.

Curated entries live in game-recipes/games/<appid>.json, one block per OS, shared with the Windows port.
`recipes_wiki.json` is generated from the whole OptiScaler wiki (`wiki.py`): every listed game with
the community verdict, its inputs, the proxy, -dx12, OptiPatcher, the OptiScaler.ini settings its
page lists and what Panel must warn about (REFramework, a copied nvngx_dlss.dll, anti-cheat, a
third-party mod, games that do not work). Hand-written entries win. Panel applies a recipe on install
and undoes exactly what it added.
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import recipe_catalog

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
    dependencies: tuple[str, ...] = ()
    catalog_revision: int | None = None
    catalog_version: int | None = None
    recommended_input: str | None = None
    effective_api: str | None = None
    quality_owner: str = "panel"
    recommended_build: str | None = None
    optiscaler_root_files: tuple[str, ...] = ()
    reframework_upscaler: bool = False
    optiscaler_fg: bool = True
    game_settings: tuple[tuple[str, str], ...] = ()
    # What the game's own menu needs so its DLSS Frame Generation reaches ANR.
    anr_settings: tuple[tuple[str, str], ...] = ()
    # With a user's mod in: the launcher Steam starts and the exe to start instead (anti-cheat off, offline play),
    # and the mod's own settings Panel turns on (file beside the exe -> `Section.Key` -> value).
    mod_launch_exe: tuple[str, str] | None = None
    mod_settings: dict[str, dict[str, str]] = field(default_factory=dict)
    # Frame generation those settings turn on inside the mod, named in the in-game pill.
    mod_frame_generation: str | None = None
    # The game's launcher deletes unknown libraries beside the exe at every start; read-only ones survive.
    protect_dlls: bool = False
    # (file under the prefix's user folder, XML element, text) set on install and put back on removal.
    game_config: tuple[tuple[str, str, str], ...] = ()
    # False when the game fails to start with FSR 4's loader in place of its FSR 3.1 amd_fidelityfx_dx12.dll.
    legacy_ffx_swap: bool = True


# Test hook: curated recipes live in game-recipes/games/<appid>.json.
RECIPES: dict[str, Recipe] = {}


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
        needs=tuple(dict.fromkeys(n for n in (*entry.get("needs", ()), *page.get("needs", ())) if n in NEEDS)),
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
                            or recipe.fg or recipe.proxy or recipe.optipatcher or recipe.wiki_settings or recipe.dependencies))


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


def recipe_for(appid: str, live: Recipe | None = None, *, engine: str = "optiscaler",
               platform: str | None = None, arch: str | None = None, game_build: str | None = None) -> Recipe | None:
    catalog = recipe_catalog.bundled()
    entry = catalog.match(appid, engine, platform, arch, game_build=game_build)
    hand = RECIPES.get(str(appid))
    if entry:
        base = hand or Recipe(entry.appid)
        hand = replace(base, exe=entry.exe or base.exe, args=entry.args, ini=dict(entry.ini),
                       proxy=entry.proxy or base.proxy, protect_dlls=entry.protect_dlls or base.protect_dlls,
                       legacy_ffx_swap=entry.legacy_ffx_swap and base.legacy_ffx_swap,
                       files=dict(entry.files) or base.files, native_dlls=entry.native_dlls or base.native_dlls,
                       needs=tuple(dict.fromkeys((*base.needs, *entry.needs))),
                       anr_settings=entry.anr_settings or base.anr_settings, game_config=entry.game_config or base.game_config,
                       mod_launch_exe=entry.mod_launch_exe or base.mod_launch_exe,
                       mod_settings={k: dict(v) for k, v in entry.mod_settings.items()} or base.mod_settings,
                       mod_frame_generation=entry.mod_frame_generation or base.mod_frame_generation,
                       fg_note=entry.fg_note or base.fg_note,
                       dependencies=entry.dependencies, catalog_revision=entry.revision,
                       catalog_version=catalog.catalog_version, source="game-recipes",
                       recommended_input=entry.recommended_input if engine == "optiscaler" else None, effective_api=entry.effective_api, quality_owner=entry.quality_owner, recommended_build=entry.recommended_build, optiscaler_root_files=entry.optiscaler_root_files,
                       reframework_upscaler=entry.reframework_upscaler, optiscaler_fg=entry.optiscaler_fg,
                       game_settings=entry.game_settings)
        # The catalog installs Luma itself; games the wiki does not list still need it named.
        if any(dep.startswith("luma-") for dep in entry.dependencies):
            hand = replace(hand, needs=tuple(dict.fromkeys((*hand.needs, "luma"))))
    return combine(hand, with_wiki(WIKI.get(str(appid)), live))


# Every RE Engine game ships its packs as re_chunk_000.pak in the game root.
RE_ENGINE_MARKER = "re_chunk_000.pak"
REFRAMEWORK = {"dinput8.dll": "reframework-nightly"}


def _dependency_files(recipe: Recipe) -> tuple[str, ...]:
    """Files a curated recipe's dependencies place, e.g. the pd-upscaler REFramework build some games need."""
    try:
        ordered = recipe_catalog.bundled().dependency_order(recipe.dependencies)
    except recipe_catalog.CatalogError:
        return ()
    return tuple(name for dependency in ordered for name in dependency.files)


def with_engine(recipe: Recipe | None, appid: str, root: Path) -> Recipe | None:
    """Compose the standard REFramework dependency from game files or known requirements."""
    if not (root / RE_ENGINE_MARKER).is_file() and not (recipe and "reframework" in recipe.needs):
        return recipe
    base = recipe or Recipe(str(appid))
    # REFramework opens its own menu with Insert too: OptiScaler's moves to Home (VK 0x24).
    keys = {"ini": {**base.ini, "Menu.ShortcutKey": "0x24"}, "menu_key": "home"}
    files = dict(base.files)
    placed = {name.lower() for name in (*files, *_dependency_files(base))}
    if "reframework-nightly" not in files.values() and "dinput8.dll" not in placed:
        files.update(REFRAMEWORK)
        placed.add("dinput8.dll")
    native_dlls = {}
    for name in (*base.native_dlls, *(("dinput8",) if "dinput8.dll" in placed else ())):
        native_dlls.setdefault(name.lower(), name)
    return replace(base, files=files, native_dlls=tuple(native_dlls.values()),
                   needs=tuple(n for n in base.needs if n != "reframework"), **keys)
