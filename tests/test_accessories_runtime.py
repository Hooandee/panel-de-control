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


def test_pausing_the_official_daemon_stops_and_disables_it_for_the_user(tmp_path):
    calls = []
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None, run=lambda argv, env: calls.append((argv, env)) or 0)
    assert rt.pause_official_app()["ok"] is True
    argv, env = calls[0]
    assert argv[:4] == ["runuser", "-u", "deck", "--"]
    assert argv[4:] == ["systemctl", "--user", "disable", "--now", "jsaux-matrix-hub.service"]
    assert env["XDG_RUNTIME_DIR"] == "/run/user/1000"


def test_pausing_reports_failure(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None, run=lambda argv, env: 1)
    assert rt.pause_official_app()["ok"] is False


def test_pausing_is_refused_off_the_steam_machine(tmp_path):
    calls = []
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="rog_ally", log=lambda *a, **k: None,
                         run=lambda argv, env: calls.append(argv) or 0)
    assert rt.pause_official_app()["ok"] is False and calls == []


def _colores(tmp_path, state):
    path = tmp_path / "Colores" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(state))
    return tmp_path / "Panel de Control"


def test_ledbar_theme_reads_the_colores_gradient(tmp_path):
    settings = _colores(tmp_path, {"mode": "effect", "color": [1, 2, 3], "effect": {"use_gradient": True},
                                   "gradient": [[255, 113, 206], [120, 115, 245], [1, 205, 254]]})
    rt = runtime.Runtime(settings_dir=settings, device_key="steam_machine", log=lambda *a, **k: None, find_panel=lambda: None)
    assert rt.ledbar_colors() == [[255, 113, 206], [120, 115, 245], [1, 205, 254]]


def test_ledbar_theme_uses_the_solid_colour_in_colour_mode(tmp_path):
    settings = _colores(tmp_path, {"mode": "color", "color": [10, 200, 30], "gradient": [[0, 0, 0], [1, 1, 1]]})
    rt = runtime.Runtime(settings_dir=settings, device_key="steam_machine", log=lambda *a, **k: None, find_panel=lambda: None)
    assert rt.ledbar_colors() == [[10, 200, 30], [10, 200, 30]]


def test_ledbar_theme_without_colores_falls_back(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path / "Panel de Control", device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None)
    assert rt.ledbar_colors() is None
    assert rt.preview("clock_digital", {"theme": "ledbar"})["frames"]


def test_ledbar_colours_reach_the_scene_palette(tmp_path):
    settings = _colores(tmp_path, {"mode": "color", "color": [10, 200, 30]})
    rt = runtime.Runtime(settings_dir=settings, device_key="steam_machine", log=lambda *a, **k: None, find_panel=lambda: None)
    palette = rt.preview("clock_digital", {"theme": "ledbar"})["palette"]
    assert [10, 200, 30] in palette
