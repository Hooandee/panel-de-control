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
