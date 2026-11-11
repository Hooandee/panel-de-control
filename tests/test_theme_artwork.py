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


ARTWORK_RPCS = (
    "_artwork_support", "_support_duo_artwork", "_support_vida_artwork", "get_duo_artwork", "set_duo_artwork",
    "get_theme_artwork", "set_theme_artwork",
)


def _artwork_plugin(settings):
    import ast
    import pathlib
    import types
    import theme_artwork

    tree = ast.parse((pathlib.Path(__file__).parents[1] / "main.py").read_text())
    plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Plugin")
    selected = [node for node in plugin.body if getattr(node, "name", "") in ARTWORK_RPCS]
    assert {node.name for node in selected} == set(ARTWORK_RPCS)
    scope = {"theme_artwork": theme_artwork, "decky": types.SimpleNamespace(logger=types.SimpleNamespace(exception=lambda *_: None))}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "main.py", "exec"), scope)
    cls = type("ArtworkPlugin", (), {name: scope[name] for name in ARTWORK_RPCS})
    state = cls()
    state._init = lambda: None
    state._settings = settings
    state._save = lambda: None
    return state


def test_rpc_general_settings_and_failed_save_rollback():
    import asyncio

    state = _artwork_plugin({"duo_artwork": {"12": VALUE}})
    general = {**VALUE, "image": None}
    assert asyncio.run(state.set_duo_artwork(0, general)) == {"ok": True}
    assert state._support_duo_artwork() == {"configured_games": 1, "general_configured": True}
    assert asyncio.run(state.set_duo_artwork(0, VALUE)) == {"ok": False, "error": "invalid_general_image"}

    def fail():
        raise OSError("disk full")

    state._save = fail
    assert asyncio.run(state.set_duo_artwork(0, None)) == {"ok": False, "error": "save_failed"}
    assert asyncio.run(state.get_duo_artwork()) == {"0": general, "12": VALUE}
    state._save = lambda: None
    assert asyncio.run(state.set_duo_artwork(0, None)) == {"ok": True}
    assert state._support_duo_artwork() == {"configured_games": 1, "general_configured": False}


def test_vida_covers_live_in_their_own_store_and_never_touch_duo():
    import asyncio

    settings = {"duo_artwork": {"12": VALUE}, "vida_artwork": {}}
    state = _artwork_plugin(settings)
    vida = {**VALUE, "positionX": 10, "scale": 180}
    assert asyncio.run(state.set_theme_artwork("vida", 12, vida)) == {"ok": True}
    assert asyncio.run(state.get_theme_artwork("vida")) == {"12": vida}
    assert asyncio.run(state.get_duo_artwork()) == {"12": VALUE}
    assert settings["duo_artwork"] == {"12": VALUE}
    assert asyncio.run(state.get_theme_artwork("duo")) == {"12": VALUE}
    assert state._support_vida_artwork() == {"configured_games": 1, "general_configured": False}
    assert asyncio.run(state.set_theme_artwork("vida", 12, None)) == {"ok": True}
    assert settings["vida_artwork"] == {} and settings["duo_artwork"] == {"12": VALUE}


def test_unknown_artwork_store_is_rejected_without_writing():
    import asyncio

    settings = {"duo_artwork": {}, "vida_artwork": {}}
    state = _artwork_plugin(settings)
    assert asyncio.run(state.set_theme_artwork("duo_artwork", 12, VALUE)) == {"ok": False, "error": "invalid_store"}
    assert asyncio.run(state.set_theme_artwork("other", 12, VALUE)) == {"ok": False, "error": "invalid_store"}
    assert asyncio.run(state.get_theme_artwork("other")) == {}
    assert settings == {"duo_artwork": {}, "vida_artwork": {}}


def test_vida_store_persists_beside_duo_across_restart(tmp_path):
    path = tmp_path / "settings.json"
    SettingsStore(path).save({"duo_artwork": {"12": VALUE}, "vida_artwork": {"13": {**VALUE, "scale": 120}}})
    loaded = SettingsStore(path).load({"duo_artwork": {}, "vida_artwork": {}})
    assert records(loaded["duo_artwork"]) == {"12": VALUE}
    assert records(loaded["vida_artwork"]) == {"13": {**VALUE, "scale": 120}}


def test_scale_is_optional_finite_and_clamped():
    assert "scale" not in normalize(VALUE)
    assert normalize({**VALUE, "scale": 150})["scale"] == 150
    assert normalize({**VALUE, "scale": 100.5})["scale"] == 100.5
    assert normalize({**VALUE, "scale": 40})["scale"] == 100
    assert normalize({**VALUE, "scale": 900})["scale"] == 300
    for bad in (True, "150", float("nan"), float("inf"), None):
        with pytest.raises(ValueError, match="invalid_scale"):
            normalize({**VALUE, "scale": bad})
    assert records({"12": {**VALUE, "scale": 999}}) == {"12": {**VALUE, "scale": 300}}


def test_logo_scale_is_optional_and_bounded():
    assert "logoScale" not in normalize(VALUE)
    assert normalize({**VALUE, "logoScale": 135})["logoScale"] == 135
    for bad in (49, 201, True, "120", float("inf")):
        with pytest.raises(ValueError, match="invalid_logo_scale"):
            normalize({**VALUE, "logoScale": bad})
    assert records({"12": {**VALUE, "logoScale": 150}}) == {"12": {**VALUE, "logoScale": 150}}


def test_logo_position_is_optional_and_bounded():
    assert "logoPositionX" not in normalize(VALUE)
    assert normalize({**VALUE, "logoPositionX": 0, "logoPositionY": 100})["logoPositionY"] == 100
    for bad in (-1, 101, True, "50", float("nan")):
        with pytest.raises(ValueError, match="invalid_logo_position"):
            normalize({**VALUE, "logoPositionY": bad})
