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
    assert rt.wants_fps(playing=True) is False
    rt.set_scene("game_heart", {})
    assert rt.wants_fps(playing=True) is True


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


def test_achievement_event_raises_an_alert_unless_turned_off(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None, find_panel=lambda: None)
    rt.set_scene("clock_digital", {})
    assert rt.notify("achievement", {"title": "Primera sangre", "icon": None}) is True
    assert rt.service._alert[0] == "alert"
    rt.service._alert = None
    rt.set_alerts({"achievements": False})
    assert rt.notify("achievement", {"title": "X"}) is False
    assert rt.state()["alerts"] == {"achievements": False}
    assert rt.notify("friend", {"title": "Kuronca"}) is False
    assert "alert" not in [scene["id"] for scene in rt.state()["catalog"]]


def test_download_event_feeds_the_download_scene(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None, find_panel=lambda: None)
    assert rt.notify("download", {"name": "Hades", "done": 50, "total": 100, "seconds": 120, "paused": False}) is True
    assert rt.preview("game_download", {})["frames"]
    assert rt.notify("download", None) is True


def test_hand_over_uses_a_clean_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEIxyz")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    calls = []
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None, run=lambda argv, env: calls.append(env) or 0)
    rt.pause_official_app()
    assert "_MEI" not in calls[0].get("LD_LIBRARY_PATH", "")


def test_official_app_activity_is_checked_and_cached(tmp_path):
    calls = []
    clock = [1000.0]
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None, run=lambda argv, env: calls.append(argv) or 0,
                         monotonic=lambda: clock[0])
    assert rt.official_active() is True
    assert rt.official_active() is True
    assert len(calls) == 1 and calls[0][-2:] == ["is-active", "jsaux-matrix-hub.service"]
    clock[0] += 61
    rt.official_active()
    assert len(calls) == 2


def test_fps_is_wanted_only_while_a_game_runs(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None, find_panel=lambda: None)
    rt.set_game_scene("game_heart")
    assert rt.wants_fps(playing=False) is False
    assert rt.wants_fps(playing=True) is True
    rt.set_game_scene(None)
    rt.set_scene("composed", {"layout": {"blocks": [{"type": "metric", "x": 0, "y": 0, "metric": "fps"}]}})
    assert rt.wants_fps(playing=True) is True


def test_wants_fps_never_waits_for_the_service_lock(tmp_path):
    import threading
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None, find_panel=lambda: None)
    rt.set_scene("game_heart", {})
    held = threading.Event()
    release = threading.Event()

    def hold():
        with rt.service._lock:
            held.set()
            release.wait(2)

    thread = threading.Thread(target=hold)
    thread.start()
    held.wait(1)
    try:
        assert rt.wants_fps(playing=True) is True
    finally:
        release.set()
        thread.join()


def test_big_drawings_are_shrunk_to_fit(tmp_path, monkeypatch):
    import random
    from accessories.jsaux_pixel import codec
    monkeypatch.setattr(codec, "MAX_GIF_BYTES", 30_000)
    rng = random.Random(1)
    frames = [base64.b64encode(bytes(rng.randrange(256) for _ in range(64 * 54 * 3))).decode() for _ in range(8)]
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None, find_panel=lambda: None)
    saved = rt.save_drawing({"name": "noise", "frames": frames, "fps": 8})
    from accessories.jsaux_pixel.scenes.custom import CustomScene
    from accessories.jsaux_pixel.scenes.base import SceneContext
    from accessories.jsaux_pixel.scenes.fit import encoded_size
    scene = CustomScene(rt._library)
    ctx = SceneContext(now=0.0, options={"drawing": saved["id"]})
    scene.key(ctx)
    assert encoded_size(scene.render(ctx)) <= 30_000


def test_image_import_rejects_a_symlink_swapped_in(tmp_path):
    home = tmp_path / "home"
    (home / "Pictures").mkdir(parents=True)
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"secret")
    (home / "Pictures" / "a.png").symlink_to(secret)
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None, user_home=home)
    assert rt.read_image(str(home / "Pictures" / "a.png"))["ok"] is False


def test_clock_follows_a_time_zone_change_without_a_restart(tmp_path):
    zoneinfo = tmp_path / "zoneinfo"
    (zoneinfo / "Europe").mkdir(parents=True)
    (zoneinfo / "Asia").mkdir(parents=True)
    (zoneinfo / "Europe" / "Madrid").write_text("x")
    (zoneinfo / "Asia" / "Tokyo").write_text("x")
    link = tmp_path / "localtime"
    link.symlink_to(zoneinfo / "Europe" / "Madrid")
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None, localtime=link)
    assert str(rt._context(0.0).tz) == "Europe/Madrid"
    link.unlink()
    link.symlink_to(zoneinfo / "Asia" / "Tokyo")
    assert str(rt._context(0.0).tz) == "Asia/Tokyo"


def test_locating_passes_the_time_zone_as_fallback(tmp_path, monkeypatch):
    zoneinfo = tmp_path / "zoneinfo" / "Europe"
    zoneinfo.mkdir(parents=True)
    (zoneinfo / "Madrid").write_text("x")
    link = tmp_path / "localtime"
    link.symlink_to(zoneinfo / "Madrid")
    seen = {}
    monkeypatch.setattr(runtime.weather, "locate", lambda zone=None: seen.setdefault("zone", zone) and {"name": "Madrid"})
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None, localtime=link)
    assert rt.locate_city() == {"city": {"name": "Madrid"}}
    assert seen["zone"] == "Europe/Madrid"


def test_locating_is_off_outside_the_steam_machine(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="rog_ally", log=lambda *a, **k: None, find_panel=lambda: None)
    assert rt.locate_city() == {"city": None}


def _rt(tmp_path, game=None, now=None):
    return runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                           find_panel=lambda: None, context_source=lambda: {"game": game} if game else {})


def test_game_info_feeds_the_pet_memory_once_per_session(tmp_path):
    game = {"appid": "10", "name": "Forza", "started_at": 1000.0}
    rt = _rt(tmp_path, game)
    info = {"appid": "10", "tags": [699, 19], "playtime_min": 600, "achievements": {"done": 3, "total": 50}}
    assert rt.notify("game_info", info) is True
    assert rt.notify("game_info", info) is True
    assert rt.pet_state()["favourite"] == "racing"
    assert rt.mind.memory["genres"] == {"racing": 1}
    assert rt._events["game_info"]["achievements"] == {"done": 3, "total": 50}


def test_game_info_is_validated(tmp_path):
    rt = _rt(tmp_path)
    assert rt.notify("game_info", {"appid": "10", "tags": "nope"}) is False
    assert rt.notify("game_info", {"tags": [1]}) is False


def test_caring_for_the_pet_answers_with_a_reaction_and_its_needs(tmp_path):
    rt = _rt(tmp_path)
    result = rt.pet_action("pet")
    assert result["reaction"] == "purr"
    assert set(result["pet"]["needs"]) == {"hunger", "energy", "fun", "love"}
    with pytest.raises(ValueError):
        rt.pet_action("hack")
    rt.rename_pet("Bolita")
    assert _rt(tmp_path).pet_state()["name"] == "Bolita"


def test_an_achievement_makes_the_pet_proud(tmp_path):
    rt = _rt(tmp_path)
    rt.set_scene("pet", {})
    rt.notify("achievement", {"title": "X"})
    assert rt.pet_state()["achievements"] == 1


def test_suspend_choice_reaches_the_service(tmp_path):
    rt = _rt(tmp_path)
    assert rt.set_on_suspend("pet")["on_suspend"] == "pet"
    rt.suspend()
    assert rt.state()["suspended"] is True
    rt.resume()
    assert rt.state()["suspended"] is False


def test_the_pet_sleeps_through_the_night_by_itself(tmp_path):
    from datetime import datetime
    rt = _rt(tmp_path)
    night = datetime(2026, 10, 22, 23, 30).astimezone().timestamp()
    rt._context(night)
    assert rt.pet_state()["asleep"] is True


def test_speedrun_controls_reset_pause_and_resume(tmp_path, monkeypatch):
    clock = [5000.0]
    monkeypatch.setattr(runtime.time, "time", lambda: clock[0])
    rt = _rt(tmp_path, {"appid": "1", "name": "Celeste", "started_at": 4000.0})
    assert rt.notify("speedrun", {"action": "reset"}) is True
    assert rt._events["speedrun"] == {"appid": "1", "origin": 5000.0, "paused_at": None}
    clock[0] = 5100.0
    rt.notify("speedrun", {"action": "pause"})
    clock[0] = 5400.0
    rt.notify("speedrun", {"action": "resume"})
    assert rt._events["speedrun"]["origin"] == 5300.0
    assert rt.notify("speedrun", {"action": "explode"}) is False


def test_a_new_game_drops_the_old_speedrun(tmp_path):
    game = {"appid": "1", "name": "A", "started_at": 4000.0}
    rt = _rt(tmp_path, game)
    rt.notify("speedrun", {"action": "reset"})
    game["appid"] = "2"
    assert "speedrun" not in rt._context(6000.0).events


def test_composing_returns_the_preview_boxes_mode_and_drops_new_pieces(tmp_path):
    rt = _rt(tmp_path)
    layout = {"blocks": [{"type": "pill", "x": 0, "y": 0, "text": "GG"}, {"type": "sticker", "x": 0, "y": 0, "sticker": "star"}]}
    result = rt.compose(layout, place=1)
    assert result["frames"] and result["mode"] == "static"
    assert len(result["boxes"]) == 2
    assert result["blocks"][1]["y"] > 0 or result["blocks"][1]["x"] > 0
    with pytest.raises(ValueError):
        rt.compose({"blocks": [{"type": "sticker", "x": 0, "y": 0, "sticker": "nuke"}]})


def test_the_sticker_book_lists_every_sticker_with_its_colours(tmp_path):
    book = _rt(tmp_path).sticker_book()
    assert "fire" in book["stickers"] and len(book["stickers"]["fire"]) == 3
    assert book["palette"]["R"] == [235, 50, 70]


def test_a_burst_of_care_rewrites_the_panel_once(tmp_path, monkeypatch):
    clock = [5000.0]
    monkeypatch.setattr(runtime.time, "time", lambda: clock[0])
    rt = _rt(tmp_path)
    rt.set_scene("pet", {})
    refreshed = []
    monkeypatch.setattr(rt.service, "refresh", lambda: refreshed.append(clock[0]))
    for kind in ("feed", "pet", "play", "pet", "pet"):
        rt.pet_action(kind)
        clock[0] += 3
    clock[0] += 60
    rt.pet_action("pet")
    assert refreshed == [5000.0, 5075.0]
