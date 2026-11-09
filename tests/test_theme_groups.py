import json

import pytest

import theme_groups

RULES = {"id": "grp:a", "name": " RPG ", "kind": "rules", "appIds": [], "added": [7], "hidden": [8],
         "rules": {"mode": "all", "rules": [{"type": "installed", "inverted": False, "params": {}}]}}
MANUAL = {"id": "grp:m", "name": "Mine", "kind": "manual", "appIds": [3, 3, 0, -1, 2**32, True, 5], "added": [], "hidden": []}


def test_valid_groups_round_trip_and_lists_are_cleaned():
    assert theme_groups.normalize_group(RULES) == {**RULES, "name": "RPG"}
    assert theme_groups.normalize_group(MANUAL)["appIds"] == [3, 5]


@pytest.mark.parametrize("value", [
    {**MANUAL, "id": ""}, {**MANUAL, "id": "a b"}, {**MANUAL, "name": "  "}, {**MANUAL, "kind": "smart"},
    {**RULES, "rules": None}, {**MANUAL, "appIds": "1,2"},
])
def test_invalid_groups_are_rejected(value):
    with pytest.raises(ValueError):
        theme_groups.normalize_group(value)


def test_unknown_rules_are_dropped_and_nesting_is_capped():
    nested = {"type": "installed", "inverted": False, "params": {}}
    for _ in range(4):
        nested = {"type": "all", "inverted": False, "params": {"mode": "all", "rules": [nested]}}
    group = theme_groups.normalize_group({**RULES, "rules": {"mode": "any", "rules": [
        {"type": "telepathy", "inverted": False, "params": {}}, nested]}})
    depth, rules = 0, group["rules"]
    while rules["rules"] and rules["rules"][0]["type"] == "all":
        depth, rules = depth + 1, rules["rules"][0]["params"]
    assert len(group["rules"]["rules"]) == 1 and depth == 3


def test_records_keep_good_ones_in_order_up_to_the_limit():
    assert [g["id"] for g in theme_groups.records([MANUAL, {"bad": 1}, RULES, MANUAL])] == ["grp:m", "grp:a"]
    many = [{**MANUAL, "id": f"grp:{i}"} for i in range(120)]
    assert len(theme_groups.records(many)) == 100


def test_accounts_stay_apart_and_bad_accounts_are_dropped():
    stored = theme_groups.store({"111": [MANUAL], "222": [RULES], "../x": [MANUAL]})
    assert list(stored) == ["111", "222"]
    assert theme_groups.summary({"111": [MANUAL], "222": [RULES]}) == {"accounts": 2, "manual": 1, "rules": 1, "imported": 0}


def test_tab_master_tabs_for_one_account(tmp_path):
    assert theme_groups.read_tab_master(tmp_path, "111") == []
    folder = tmp_path / "TabMaster"
    folder.mkdir()
    (folder / "settings.json").write_text(json.dumps({"usersDict": {"111": {"tabs": {
        "abc": {"title": "RPG", "filters": [{"type": "installed", "params": {"installed": True}}]},
        "AllGames": {"title": "All", "position": 0}}}}}))
    tabs = theme_groups.read_tab_master(tmp_path, "111")
    assert [t["id"] for t in tabs] == ["abc", "AllGames"] and tabs[0]["title"] == "RPG"
    assert theme_groups.read_tab_master(tmp_path, "222") == []
    (folder / "settings.json").write_text("{broken")
    assert theme_groups.read_tab_master(tmp_path, "111") == []


def test_rpc_store_per_account_and_failed_save_rolls_back():
    import ast
    import asyncio
    import pathlib
    import types

    tree = ast.parse((pathlib.Path(__file__).parents[1] / "main.py").read_text())
    plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Plugin")
    selected = [node for node in plugin.body if getattr(node, "name", "") in ("get_theme_groups", "set_theme_groups")]
    scope = {"theme_groups": theme_groups, "decky": types.SimpleNamespace(logger=types.SimpleNamespace(exception=lambda _: None))}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "main.py", "exec"), scope)
    state = types.SimpleNamespace(_init=lambda: None, _settings={}, _save=lambda: None)
    assert asyncio.run(scope["set_theme_groups"](state, "111", [MANUAL, {"bad": 1}]))["ok"]
    assert [g["id"] for g in asyncio.run(scope["get_theme_groups"](state, "111"))] == ["grp:m"]
    assert asyncio.run(scope["get_theme_groups"](state, "222")) == []
    assert asyncio.run(scope["set_theme_groups"](state, "x", []))["ok"] is False

    def fail():
        raise OSError("disk")
    state._save = fail
    assert asyncio.run(scope["set_theme_groups"](state, "111", [RULES])) == {"ok": False, "error": "save_failed"}
    assert [g["id"] for g in asyncio.run(scope["get_theme_groups"](state, "111"))] == ["grp:m"]


def test_params_are_measured_compactly_like_the_frontend():
    ids = [str(76561197960287930 + i) for i in range(200)]
    params = {"ids": ids, "match": "any"}
    compact = json.dumps(params, separators=(",", ":"))
    assert len(compact) <= theme_groups.MAX_PARAMS_BYTES < len(json.dumps(params))
    group = {"id": "grp:f", "name": "Friends", "kind": "rules", "appIds": [], "added": [], "hidden": [],
             "rules": {"mode": "all", "rules": [{"type": "friends", "inverted": False, "params": params}]}}
    assert theme_groups.normalize_group(group)["rules"]["rules"][0]["params"]["ids"] == ids


def test_null_lists_and_damaged_records_cost_only_themselves():
    good = {"id": "grp:a", "name": "A", "kind": "manual", "appIds": [10], "added": None, "hidden": None}
    damaged = {"id": "grp:b", "name": "B", "kind": "rules", "appIds": [], "added": [], "hidden": [],
               "include": [["music"], "music"], "rules": {"mode": "all", "rules": [{"type": "installed", "inverted": False, "params": {}}]}}
    out = theme_groups.records([good, damaged])
    assert [g["id"] for g in out] == ["grp:a", "grp:b"]
    assert out[1]["include"] == ["music"]
