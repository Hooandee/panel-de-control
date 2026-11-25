from ambient.core.collections import (
    SUGGESTED_BACKGROUNDS,
    add_favorite,
    remove_item,
    restore_suggested,
    visible_backgrounds,
)
from ambient.core.settings import default_settings


def test_defaults_show_all_suggested():
    ids = [c["id"] for c in visible_backgrounds(default_settings())]
    assert ids == [s["id"] for s in SUGGESTED_BACKGROUNDS]


def test_removed_suggested_hidden_and_restorable():
    settings = remove_item(default_settings(), "background", "suggested.nasa")
    assert "suggested.nasa" not in [c["id"] for c in visible_backgrounds(settings)]
    assert "suggested.nasa" not in settings["background"]["collections"]
    restored = restore_suggested(settings, "background")
    assert "suggested.nasa" in [c["id"] for c in visible_backgrounds(restored)]


def test_restoring_one_suggestion_brings_back_only_it_and_shows_it():
    settings = remove_item(default_settings(), "background", "suggested.nasa")
    settings = remove_item(settings, "background", "suggested.bing")
    restored = restore_suggested(settings, "background", "suggested.nasa")
    ids = [c["id"] for c in visible_backgrounds(restored)]
    assert "suggested.nasa" in ids and "suggested.bing" not in ids
    assert "suggested.nasa" in restored["background"]["collections"]


def test_add_favorite_appends_and_dedupes():
    settings = add_favorite(default_settings(), "background", "https://x.test/a.jpg", "Mi cielo")
    settings = add_favorite(settings, "background", "https://x.test/a.jpg", "Otra vez")
    favs = [c for c in visible_backgrounds(settings) if c["kind"] == "favorite"]
    assert len(favs) == 1
    assert favs[0]["name"] == "Mi cielo"
    assert favs[0]["id"].startswith("fav.")


def test_add_favorite_rejects_non_http():
    settings = default_settings()
    assert add_favorite(settings, "background", "javascript:alert(1)", "x") == settings


def test_remove_favorite():
    settings = add_favorite(default_settings(), "radio", "https://r.test/stream", "Radio")
    fav_id = settings["radio"]["favorites"][0]["id"]
    assert remove_item(settings, "radio", fav_id)["radio"]["favorites"] == []


def test_folder_collections_listed():
    settings = default_settings()
    settings["collections"]["folders"] = ["/home/deck/Pictures/Fondos"]
    folder = [c for c in visible_backgrounds(settings) if c["kind"] == "folder"][0]
    assert folder["name"] == "Fondos"
    assert folder["id"].startswith("folder.")


def test_inputs_not_mutated():
    settings = default_settings()
    add_favorite(settings, "background", "https://x.test/a.jpg", "a")
    assert settings["collections"]["favorites"] == []
