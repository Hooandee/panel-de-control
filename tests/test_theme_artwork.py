import pytest
from theme_artwork import normalize, records
from settings_store import SettingsStore

VALUE = {"source": "hero", "image": "https://steamloopback.host/customimages/12_hero.png", "positionX": 25, "positionY": 80, "showLogo": True, "showTitle": False}


def test_restart_and_reset(tmp_path):
    path = tmp_path / "settings.json"
    SettingsStore(path).save({"duo_artwork": {"12": VALUE}})
    store = SettingsStore(path)
    assert records(store.load({"duo_artwork": {}})["duo_artwork"]) == {"12": VALUE}
    store.save({"duo_artwork": {}})
    assert SettingsStore(path).load({"duo_artwork": {}})["duo_artwork"] == {}


@pytest.mark.parametrize("field,value", [("image", "https://example.com/x.png"), ("image", "https://steamloopback.host.evil/assets/1/x.png"), ("positionX", -1), ("positionY", 101), ("positionX", float("nan")), ("showLogo", 1), ("source", "external")])
def test_reject_invalid_records(field, value):
    with pytest.raises(ValueError):
        normalize({**VALUE, field: value})


def test_corrupt_settings_degrade_without_losing_valid_games():
    assert records({"12": VALUE, "13": {"image": "broken"}, "bad": VALUE}) == {"12": VALUE}


def test_reject_path_traversal():
    with pytest.raises(ValueError):
        normalize({**VALUE, "image": "https://steamloopback.host/assets/%2e%2e/config/x"})


def test_general_settings_persist_alongside_existing_game_settings(tmp_path):
    general = {**VALUE, "image": None}
    path = tmp_path / "settings.json"
    SettingsStore(path).save({"duo_artwork": {"0": general, "12": VALUE}})
    assert records(SettingsStore(path).load({"duo_artwork": {}})["duo_artwork"]) == {"0": general, "12": VALUE}


def test_general_settings_reject_game_image_without_losing_game_records():
    with pytest.raises(ValueError, match="invalid_general_image"):
        normalize(VALUE, general=True)
    assert records({"0": VALUE, "12": VALUE}) == {"12": VALUE}


def test_rpc_general_settings_and_failed_save_rollback():
    import ast
    import asyncio
    import pathlib
    import types
    import theme_artwork

    tree = ast.parse((pathlib.Path(__file__).parents[1] / "main.py").read_text())
    plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Plugin")
    selected = [node for node in plugin.body if getattr(node, "name", "") in ("set_duo_artwork", "get_duo_artwork", "_support_duo_artwork")]
    scope = {"theme_artwork": theme_artwork, "decky": types.SimpleNamespace(logger=types.SimpleNamespace(exception=lambda _: None))}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "main.py", "exec"), scope)
    state = types.SimpleNamespace(_init=lambda: None, _settings={"duo_artwork": {"12": VALUE}}, _save=lambda: None)
    general = {**VALUE, "image": None}
    assert asyncio.run(scope["set_duo_artwork"](state, 0, general)) == {"ok": True}
    assert scope["_support_duo_artwork"](state) == {"configured_games": 1, "general_configured": True}
    assert asyncio.run(scope["set_duo_artwork"](state, 0, VALUE)) == {"ok": False, "error": "invalid_general_image"}

    def fail():
        raise OSError("disk full")

    state._save = fail
    assert asyncio.run(scope["set_duo_artwork"](state, 0, None)) == {"ok": False, "error": "save_failed"}
    assert asyncio.run(scope["get_duo_artwork"](state)) == {"0": general, "12": VALUE}
    state._save = lambda: None
    assert asyncio.run(scope["set_duo_artwork"](state, 0, None)) == {"ok": True}
    assert scope["_support_duo_artwork"](state) == {"configured_games": 1, "general_configured": False}
