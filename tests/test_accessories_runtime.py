import base64

import pytest

from accessories.jsaux_pixel import runtime


def test_runtime_is_off_outside_the_steam_machine(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_deck_oled", log=lambda *a, **k: None)
    state = rt.state()
    assert state["supported"] is False
    assert state["present"] is False
    rt.start()
    assert rt.worker is None


def test_catalog_lists_every_scene_with_category_and_label(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None)
    catalog = rt.state()["catalog"]
    ids = [scene["id"] for scene in catalog]
    assert {"fw_tunnel", "fw_dodecahedron", "fw_fireworks", "fw_desert"} <= set(ids)
    assert len(ids) == len(set(ids))
    assert all(scene["category"] and scene["labelKey"].startswith("accessories.scene.") for scene in catalog)


def test_preview_returns_decodable_frames(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None)
    fw = rt.preview("fw_fireworks", {})
    assert fw["firmwareAnimation"] == 2
    for scene in rt.state()["catalog"]:
        preview = rt.preview(scene["id"], {})
        for frame in preview["frames"]:
            assert len(base64.b64decode(frame)) == 64 * 54
        assert len(preview["frames"]) == len(preview["delays"]) <= runtime.PREVIEW_MAX_FRAMES


def test_unknown_scene_raises(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None)
    with pytest.raises(ValueError):
        rt.set_scene("nope", {})


def test_game_art_event_reaches_the_cover_scene_and_is_validated(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None, context_source=lambda: {"game": {"appid": "10", "name": "X"}})
    good = base64.b64encode(bytes([200, 10, 10]) * (64 * 54)).decode()
    assert rt.notify("game_art", {"appid": "10", "rgb": good}) is True
    assert rt.notify("game_art", {"appid": "10", "rgb": "short"}) is False
    assert rt.notify("unknown", {}) is False
    preview = rt.preview("game_cover", {})
    first = base64.b64decode(preview["frames"][0])
    assert preview["palette"][first[0]] == [200, 10, 10]


def test_context_merges_system_readings_with_panel_values(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None, context_source=lambda: {"metrics": {"fps": 99.0}},
                         system_metrics=lambda: {"gpu_w": 80.0, "fps": None})
    ctx = rt._context(0.0)
    assert ctx.metrics == {"gpu_w": 80.0, "fps": 99.0}


def test_only_live_scenes_ask_for_frame_rate(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None)
    rt.set_scene("clock_digital", {})
    assert rt.wants_fps() is False
    rt.set_scene("game_heart", {})
    assert rt.wants_fps() is True


def test_catalog_declares_each_scene_options(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None)
    options = {scene["id"]: scene["options"] for scene in rt.state()["catalog"]}
    assert options["clock_digital"] == ["theme", "hour12"]
    assert options["art_lava"] == ["theme"]
    assert options["fw_tunnel"] == []
    assert options["hooandee"] == []


def test_drawings_round_trip_through_the_runtime(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None)
    frame = base64.b64encode(bytes([9, 9, 9]) * (64 * 54)).decode()
    saved = rt.save_drawing({"name": "Yo", "frames": [frame], "fps": 6})
    assert saved["ok"] and [d["name"] for d in rt.list_drawings()["drawings"]] == ["Yo"]
    assert rt.preview("custom", {"drawing": saved["id"]})["frames"]
    assert rt.delete_drawing(saved["id"])["ok"]
    assert rt.list_drawings()["drawings"] == []
    assert rt.save_drawing({"name": "bad", "frames": [], "fps": 6})["ok"] is False


def test_image_import_reads_only_pictures_under_home(tmp_path):
    home = tmp_path / "home"
    (home / "Pictures").mkdir(parents=True)
    (home / "Pictures" / "a.png").write_bytes(b"\x89PNGdata")
    (home / "notes.txt").write_text("x")
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None, user_home=home)
    ok = rt.read_image(str(home / "Pictures" / "a.png"))
    assert ok["ok"] and base64.b64decode(ok["data"]) == b"\x89PNGdata" and ok["mime"] == "image/png"
    assert rt.read_image(str(home / "notes.txt"))["ok"] is False
    assert rt.read_image("/etc/passwd")["ok"] is False
    assert rt.read_image(str(home / "Pictures" / ".." / ".." / "x.png"))["ok"] is False
