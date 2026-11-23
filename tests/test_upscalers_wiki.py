import io
import json
import urllib.error

from upscalers import wiki

TABLE = """| Game | Compatibility | Upscaler <br>Inputs | OptiPatcher <br>Support | Notes | Images |
| ---- | :-----------: | :-----------------: | :---: | ----- | :----: |
| [Stellar Blade](Stellar-Blade) | ✅ | DLSS, FSR3.1 |  | Launch with -dx12 and use OptiScaler as `winmm.dll`. | |
| Some Racer | ❌ | FSR2 |  | EAC blocks it | |
| Quiet Game | ✅ | DLSS | ✨ |  | |
"""


class Response(io.BytesIO):
    def __init__(self, body, etag='"v1"'):
        super().__init__(body)
        self.headers = {"ETag": etag}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_rows_are_matched_by_name_ignoring_marks_and_demo():
    rows = wiki.parse(TABLE)
    cache = wiki.WikiCache.__new__(wiki.WikiCache)
    cache._rows = rows
    assert cache.lookup("Stellar Blade™ Demo") == {"name": "Stellar Blade", "status": "works", "args": ["-dx12"],
                                                   "proxy": "winmm.dll", "inputs": ["DLSS", "FSR3.1"], "page": "Stellar-Blade"}
    assert cache.lookup(None, "Some Racer") == {"name": "Some Racer", "status": "broken", "inputs": ["FSR2"]}
    assert cache.lookup("Quiet Game")["optipatcher"] is True
    assert cache.lookup("Unknown") is None


# Public compatibility row: https://github.com/optiscaler/OptiScaler/wiki/Compatibility-List
VILLAGE_ROW = """## Upscaler mods support
| [Resident Evil 8 Village](Resident-Evil-8-Village) | ✅ | DLSS, XeSS | Requires REFramework mod (pd-upscaler branch) + PDUpscaler plugin + OptiScaler | |
"""


def test_village_steam_title_finds_the_public_wiki_requirements():
    from upscalers import auto_recipes, recipes

    cache = wiki.WikiCache.__new__(wiki.WikiCache)
    cache._rows = wiki.parse(VILLAGE_ROW)
    found = cache.lookup("Resident Evil Village")
    assert found["page"] == "Resident-Evil-8-Village"
    assert found["needs"] == ["reframework", "mod"]
    live = recipes.from_facts("1196590", found, "optiscaler-wiki@live")
    linux = {"platform": "linux", "arch": "x86_64"}
    for recipe in (recipes.recipe_for("1196590", **linux), recipes.recipe_for("1196590", live, **linux)):
        assert recipe.needs == ("reframework", "mod")
        assert recipe.inputs == ("DLSS", "XeSS")
        # The wiki's mod is the curated PureDark route: Panel brings REFramework, the user the Nexus plugin.
        assert recipe.dependencies == ("refw-pdup-re8", "puredark-upscaler-base")
        assert auto_recipes.unresolved(recipe, {"inputs": {}}, None)


def test_current_wiki_title_wins_over_the_village_alias():
    cache = wiki.WikiCache.__new__(wiki.WikiCache)
    cache._rows = wiki.parse(VILLAGE_ROW)
    current = {"name": "Resident Evil Village", "needs": ["mod"], "inputs": ["XeSS"]}
    cache._rows[wiki.clean(current["name"])] = current
    assert cache.lookup("Resident Evil Village") is current
    assert cache.lookup("Resident Evil Village Demo") is current
    assert cache.lookup("Resident Evil Village 2") is None


def test_refresh_downloads_once_then_keeps_the_copy_when_offline(tmp_path):
    cache = wiki.WikiCache(tmp_path)
    clock = [1000.0]
    assert cache.refresh(fetch=lambda *a, **k: Response(TABLE.encode()), now=lambda: clock[0]) == {"updated": True, "fresh": True}
    assert cache.refresh(fetch=lambda *a, **k: (_ for _ in ()).throw(AssertionError("too soon")), now=lambda: clock[0]) == {
        "updated": False, "fresh": True}
    clock[0] += wiki.MAX_AGE_S + 1

    def offline(*a, **k):
        raise OSError("no network")

    assert cache.refresh(fetch=offline, now=lambda: clock[0]) == {"updated": False, "fresh": False}
    assert wiki.WikiCache(tmp_path).lookup("Stellar Blade") is not None

    def unchanged(request, **k):
        assert request.get_header("If-none-match") == '"v1"'
        raise urllib.error.HTTPError(request.full_url, 304, "Not Modified", {}, None)

    assert cache.refresh(fetch=unchanged, now=lambda: clock[0]) == {"updated": False, "fresh": True}
    assert json.loads((tmp_path / "optiscaler-wiki.json").read_text())["fetched_at"] == clock[0]


MODS = """## Upscaler mods support
| Game | Compatibility | Upscaler <br>Inputs | Notes  | Images |
| ---- | :-----------: | :-----------------: | ------ | :----: |
| [Persona 5 Royal](Persona-5-Royal) | ✅ | DLSS | Requires Luma mod, check the entry | |
| [Resident Evil 2 (2019)](Resident-Evil-2-(2019)) | ✅ | DLSS, XeSS | Requires REFramework mod (pd-upscaler branch) | |
| [Elden Ring](Elden-Ring-(ERSS‐FG)) | ✅ | FSR3.1 | Use ERSS-FG mod as basis | |
"""

PAGE = """[cols="1,1"]
|===
|**Filename**
|`winmm.dll`, `OptiScaler.asi`

|**OS**
|SteamOS with Proton GE

|**Settings**
a|
* `Dxgi=false` if on AMD/Intel + `DontUseNTShared=true`
* For Vulkan:
** `Vulkan = true` in OptiScaler.ini
* `HUDFix=true` (OptiFG)
* `OverlayMenu=false` _(autoapplied since Opti 0.9)_

|**Known Issues**
a|
* Something
|===
"""

INI = """[Spoofing]
; true or false - Default (auto) is true
Dxgi=auto
[Menu]
; true or false - Default (auto) is true
OverlayMenu=auto
[Hudfix]
; true or false - Default (auto) is false
HUDFix=auto
[Plugins]
; Integer value
LateAsiPluginsDelay=auto
"""


def test_mod_tables_say_what_the_game_needs():
    rows = wiki.parse(MODS)
    assert rows["persona 5 royal"]["needs"] == ["luma"]
    assert rows["resident evil 2 2019"]["needs"] == ["reframework", "mod"]
    assert rows["resident evil 2 2019"]["page"] == "Resident-Evil-2-(2019)"
    assert rows["elden ring"]["needs"] == ["mod"]


def test_page_settings_split_plain_from_conditional_and_skip_autoapplied():
    facts = wiki.parse_page(PAGE)
    assert facts == {"proxy": "winmm.dll", "linux": True,
                     "settings": {"Dxgi": "false", "DontUseNTShared": "true"},
                     "suggestions": {"Vulkan": "true", "HUDFix": "true"}}


RE4_PAGE = """[cols="1,1"]
|===
|**Upscaler Inputs**
|DLSS, XeSS (read notes), +++<s>FSR2</s>+++

|**Notes**
a|
* *To get OptiScaler to work with REFramework + UpscalerBasePlugin*:
. Download PureDark's UpscalerBasePlugin **1.1.2**.
** *PDPerfPlugin.dll* _from UpscalerBasePlugin also goes onto the root_
|===
"""


def test_page_that_asks_for_puredarks_plugin_needs_a_separate_mod():
    from upscalers import recipes
    facts = wiki.parse_page(RE4_PAGE)
    assert facts["needs"] == ["mod"]
    recipe = recipes.from_facts("2050650", {"status": "works", "needs": ["reframework"]}, "test", facts)
    assert recipe.needs == ("reframework", "mod")
    assert "needs" not in wiki.parse_page(PAGE)


def test_row_keeps_parenthesised_page_names_and_the_puredark_requirement():
    row = ("| [Resident Evil 4 (2023)](Resident-Evil-4-(2023)) | ✅ | DLSS, XeSS | | Requires REFramework mod "
           "(pd-upscaler branch) + PDUpscaler plugin + OptiScaler, check [Wiki](Resident-Evil-4-(2023)) | |")
    found = wiki.parse(TABLE.splitlines()[0] + "\n|---|---|---|---|---|---|\n" + row)["resident evil 4 2023"]
    assert found["page"] == "Resident-Evil-4-(2023)"
    assert found["needs"] == ["reframework", "mod"]


def test_page_cached_by_an_older_parser_is_fetched_whole_again(tmp_path):
    (tmp_path / "optiscaler-wiki-pages.json").write_text(json.dumps(
        {"RE4": {"facts": {}, "etag": "old", "fetched_at": 1e6}}))
    cache = wiki.WikiCache(tmp_path)
    seen = []

    def fetch(request, **_):
        seen.append(request.get_header("If-none-match"))
        return Response(RE4_PAGE.encode())

    assert cache.refresh_page("RE4", fetch=fetch, now=lambda: 1e6 + 10)["updated"]
    assert seen == [None] and cache.page_facts("RE4")["needs"] == ["mod"]


def test_settings_resolve_only_to_one_known_key_with_an_accepted_value():
    assert wiki.resolve_settings(INI, {"Dxgi": "false", "HUDFix": "maybe", "Missing": "1", "LateAsiPluginsDelay": "500"}) == {
        "Spoofing.Dxgi": "false", "Plugins.LateAsiPluginsDelay": "500"}


def test_page_is_fetched_once_a_day_and_kept_offline(tmp_path):
    cache = wiki.WikiCache(tmp_path)
    clock = [1e6]
    assert cache.refresh_page("Stellar-Blade", fetch=lambda *a, **k: Response(PAGE.encode()), now=lambda: clock[0])["updated"]
    assert cache.page_facts("Stellar-Blade")["proxy"] == "winmm.dll"
    assert cache.refresh_page("../etc", fetch=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no")))["updated"] is False
    clock[0] += wiki.PAGE_MAX_AGE_S + 1

    def offline(*a, **k):
        raise OSError("no network")

    assert cache.refresh_page("Stellar-Blade", fetch=offline, now=lambda: clock[0]) == {"updated": False, "fresh": False}
    assert wiki.WikiCache(tmp_path).page_facts("Stellar-Blade")["linux"] is True


def test_a_copy_saved_in_an_older_format_is_ignored_and_fetched_again(tmp_path):
    (tmp_path / "optiscaler-wiki.json").write_text(json.dumps({"rows": {"stellar blade": {"optipatcher": True}}, "fetched_at": 9e12}))
    cache = wiki.WikiCache(tmp_path)
    assert cache.lookup("Stellar Blade") is None
    assert cache.refresh(fetch=lambda *a, **k: Response(TABLE.encode()), now=lambda: 1000.0)["updated"]
    assert cache.lookup("Stellar Blade")["status"] == "works"


def test_use_dx12_note_adds_the_dx12_argument():
    # Wiki notes such as Satisfactory's ("Use DX12 and install to ...") ask for DX12 without the literal flag.
    for note in ("Use DX12 and install to `Satisfactory/` `Engine/` `Binaries/` `Win64/`.", "Use DX12 mode", "Use DX12, requires enabling Non-Linear sRGB Input for FSR4."):
        assert wiki.facts("✅", "", note)["args"] == ["-dx12"]
    assert "args" not in wiki.facts("✅", "", "DX11 only, do not use the DX12 path")
