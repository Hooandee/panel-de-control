import copy
import json
from pathlib import Path

import pytest

from ambient.core.settings import SETTINGS_VERSION, normalize_settings

FIXTURES = Path(__file__).resolve().parent.parent / "shared" / "contracts" / "ambient" / "fixtures"
DEFAULTS = json.loads((FIXTURES / "defaults.json").read_text())
CASES = json.loads((FIXTURES / "normalization-cases.json").read_text())


def _merge(base, patch):
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict) and key not in ("perGame", "claims"):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_normalization_contract(case):
    expected = DEFAULTS if case.get("expect") == "defaults" else _merge(DEFAULTS, case["patch"])
    assert normalize_settings(case["input"]) == expected


def test_version_matches_contract():
    assert DEFAULTS["version"] == SETTINGS_VERSION


def test_non_dict_input_yields_defaults():
    assert normalize_settings(None) == DEFAULTS
    assert normalize_settings([1, 2]) == DEFAULTS


def test_normalize_is_idempotent():
    once = normalize_settings({"version": 1, "background": {"intervalSec": 45}})
    assert normalize_settings(once) == once


def test_levels_come_from_old_choices_and_are_clamped():
    from ambient.core.settings import normalize_settings

    old = normalize_settings({"music": {"inGameMusic": "duck", "inGameRadio": "pause", "videoSize": "large"}})["music"]
    assert (old["inGameMusicLevel"], old["inGameRadioLevel"], old["videoScale"]) == (30, 0, 52)
    new = normalize_settings({"music": {"inGameMusicLevel": 250, "inGameRadioLevel": -4, "videoScale": 5}})["music"]
    assert (new["inGameMusicLevel"], new["inGameRadioLevel"], new["videoScale"]) == (100, 0, 20)


def test_pinned_background_keeps_only_media_refs():
    assert normalize_settings({"background": {"pinned": "local:abc"}})["background"]["pinned"] == "local:abc"
    assert normalize_settings({"background": {"pinned": "javascript:x"}})["background"]["pinned"] == ""
    assert normalize_settings({})["background"]["pinned"] == ""


def test_selected_backgrounds_keep_unique_original_refs_in_selection_order():
    raw = {"background": {"selectedRefs": ["local:first", "remote:https://example.test/a.jpg", "local:first", "steam:10", "opt:copy", "url:copy", "javascript:x", "local:", None, 12, "local:bad\n"]}}
    assert normalize_settings(raw)["background"]["selectedRefs"] == ["local:first", "remote:https://example.test/a.jpg", "steam:10"]


@pytest.mark.parametrize("selected", [None, {}, "local:first"])
def test_invalid_selection_preserves_collection_fallback(selected):
    normalized = normalize_settings({"background": {"selectedRefs": selected, "collections": ["suggested.bing"]}})
    assert normalized["background"]["selectedRefs"] == []
    assert normalized["background"]["collections"] == ["suggested.bing"]


def test_selected_backgrounds_do_not_silently_truncate_large_selections():
    refs = [f"local:photo-{number}" for number in range(250)]
    assert normalize_settings({"background": {"selectedRefs": refs}})["background"]["selectedRefs"] == refs


def test_old_settings_have_no_explicit_selection():
    assert normalize_settings({"version": 1})["background"]["selectedRefs"] == []


def test_media_level_starts_from_the_old_radio_level_and_game_at_full():
    music = normalize_settings({"music": {"inGameRadio": "duck"}})["music"]
    assert music["inGameMediaLevel"] == 30
    assert music["inGameGameLevel"] == 100
    assert normalize_settings({"music": {"inGameGameLevel": 250}})["music"]["inGameGameLevel"] == 100


def test_a_fresh_install_leaves_steam_home_untouched_until_the_background_is_switched_on():
    fresh = normalize_settings({})
    assert fresh["background"]["enabled"] is False
    assert fresh["background"]["collections"] == ["suggested.library"]
