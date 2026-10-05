import array
import shutil
import tempfile
import http.server
import json
import os
import socket
import struct
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py_modules", "kiosk", "native"))

import choices  # noqa: E402
import drm  # noqa: E402
import geometry  # noqa: E402
import lights  # noqa: E402
import rpc  # noqa: E402
import touch  # noqa: E402

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
BTN_TOUCH, ABS_MT_SLOT, ABS_MT_X, ABS_MT_Y, ABS_MT_TRACKING_ID = 0x14A, 0x2F, 0x35, 0x36, 0x39


def ev(kind, code, value):
    return struct.pack("llHHi", 0, 0, kind, code, value)


def syn():
    return ev(EV_SYN, 0, 0)


def test_touch_parser_reports_down_move_up_of_the_first_finger_in_panel_pixels():
    parser = touch.TouchParser(scale_x=0.5, scale_y=2.0)
    events = parser.feed(
        ev(EV_ABS, ABS_MT_TRACKING_ID, 7) + ev(EV_ABS, ABS_MT_X, 100) + ev(EV_ABS, ABS_MT_Y, 40)
        + ev(EV_KEY, BTN_TOUCH, 1) + syn()
        + ev(EV_ABS, ABS_MT_X, 120) + syn()
        + syn()
        + ev(EV_ABS, ABS_MT_TRACKING_ID, -1) + ev(EV_KEY, BTN_TOUCH, 0) + syn()
    )
    assert [(e.kind, e.x, e.y) for e in events] == [("down", 50, 80), ("move", 60, 80), ("up", 60, 80)]


def test_touch_parser_starts_from_the_devices_current_position():
    # The input core drops a repeated position: a tap where the last one lifted carries no coordinates.
    parser = touch.TouchParser(scale_x=1.0, scale_y=1.0, x=368, y=337)
    events = parser.feed(ev(EV_ABS, ABS_MT_TRACKING_ID, 9) + ev(EV_KEY, BTN_TOUCH, 1) + syn())
    assert [(e.kind, e.x, e.y) for e in events] == [("down", 368, 337)]


def test_touch_parser_ignores_other_fingers_and_split_reads():
    parser = touch.TouchParser()
    stream = (
        ev(EV_ABS, ABS_MT_TRACKING_ID, 1) + ev(EV_ABS, ABS_MT_X, 10) + ev(EV_ABS, ABS_MT_Y, 10) + syn()
        + ev(EV_ABS, ABS_MT_SLOT, 1) + ev(EV_ABS, ABS_MT_TRACKING_ID, 2) + ev(EV_ABS, ABS_MT_X, 900) + syn()
        + ev(EV_ABS, ABS_MT_SLOT, 0) + ev(EV_ABS, ABS_MT_TRACKING_ID, -1) + syn()
    )
    events = []
    for cut in range(0, len(stream), 5):
        events += parser.feed(stream[cut:cut + 5])
    assert [(e.kind, e.x) for e in events] == [("down", 10), ("up", 10)]


def test_find_device_matches_the_input_name(tmp_path):
    for entry, name in (("event4", "top_touchscreen"), ("event5", "bottom_touchscreen"), ("mouse0", "x")):
        (tmp_path / entry / "device").mkdir(parents=True)
        (tmp_path / entry / "device" / "name").write_text(name + "\n")
    assert touch.find_device("bottom_touchscreen", str(tmp_path)) == "/dev/input/event5"
    assert touch.find_device("missing", str(tmp_path)) is None


@pytest.fixture
def short_dir():
    # AF_UNIX paths are capped at about 100 bytes; pytest's tmp_path on macOS is longer.
    path = tempfile.mkdtemp(dir="/tmp")
    yield path
    shutil.rmtree(path, ignore_errors=True)


def test_receive_lease_takes_the_fd_and_keeps_the_socket_open(short_dir):
    path = os.path.join(short_dir, "lease.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    shared_r, shared_w = os.pipe()

    def serve():
        conn, _ = server.accept()
        conn.sendmsg([b"L"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [shared_w]))])
        conn.recv(1)
        conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    sock, fd = drm.receive_lease(path)
    os.write(fd, b"x")
    assert os.read(shared_r, 1) == b"x"
    assert sock.fileno() >= 0
    sock.close()
    thread.join(2)
    server.close()


def test_receive_lease_without_an_fd_is_an_error(short_dir):
    path = os.path.join(short_dir, "lease.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    threading.Thread(target=lambda: server.accept()[0].sendall(b"L"), daemon=True).start()
    with pytest.raises(drm.LeaseError):
        drm.receive_lease(path)
    server.close()


class _Kiosk(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Kiosk.seen.append((self.headers.get(rpc.TOKEN_HEADER), body))
        reply = {"error": "unknown_method"} if body["method"] == "nope" else {"result": body["args"]}
        payload = json.dumps(reply).encode()
        self.send_response(404 if "error" in reply else 200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def kiosk_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Kiosk)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _Kiosk.seen = []
    yield server
    server.shutdown()
    server.server_close()


def test_panel_rpc_sends_the_token_and_returns_results(kiosk_server):
    client = rpc.PanelRpc(f"http://127.0.0.1:{kiosk_server.server_address[1]}/?k=secret")
    assert client.call("get_kiosk_live", 1, "a") == [1, "a"]
    assert client.call("other") == []
    assert _Kiosk.seen == [("secret", {"method": "get_kiosk_live", "args": [1, "a"]}), ("secret", {"method": "other", "args": []})]
    with pytest.raises(rpc.RpcError):
        client.call("nope")


def test_panel_rpc_reports_an_unreachable_panel():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    with pytest.raises(rpc.RpcError):
        rpc.PanelRpc(f"http://127.0.0.1:{port}/?k=t").call("get_kiosk_live")


def test_grid_matches_the_web_layout_and_tiles_do_not_overlap():
    rects = geometry.grid_rects()
    assert rects["perf"].x == geometry.GRID_X and rects["perf"].y == geometry.GRID_Y
    assert round(rects["vol"].x + rects["vol"].w, 6) == geometry.GRID_X + geometry.GRID_W
    assert round(rects["off"].y + rects["off"].h, 6) == geometry.GRID_Y + geometry.GRID_H
    names = list(rects)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ra, rb = rects[a], rects[b]
            assert ra.x + ra.w <= rb.x or rb.x + rb.w <= ra.x or ra.y + ra.h <= rb.y or rb.y + rb.h <= ra.y, (a, b)


@pytest.mark.parametrize("point", [(0, 0), (620, 540), (100, 400), (612.5, 3.25)])
def test_rotation_and_touch_mapping_are_inverse(point):
    panel_w, panel_h = 1080, 1240
    xx, yx, xy, yy, x0, y0 = geometry.rotation(panel_w, panel_h)
    lx, ly = point
    px, py = xx * lx + xy * ly + x0, yx * lx + yy * ly + y0
    assert 0 <= px <= panel_w and 0 <= py <= panel_h
    back = geometry.logical_point(px, py, panel_w, panel_h)
    assert back == pytest.approx(point)


def test_top_left_of_the_deck_lands_on_the_panel_edge_the_landscape_top_faces():
    # Mounted a quarter turn clockwise: the deck's top edge is the panel's right (x = width) edge.
    assert geometry.logical_point(1080, 0, 1080, 1240) == (0, 0)


def test_fps_choices_match_the_web_kiosk():
    assert choices.fps_choices(60) == [30, 40, 45, 60]
    assert choices.fps_choices(None) == [30, 40, 45, 60]
    assert choices.fps_choices(144) == [40, 60, 90, 120, 144]
    assert choices.fps_choices(10) == []


def test_refresh_choices_hide_a_range_steam_will_not_switch():
    assert choices.refresh_choices({"min": 60, "max": 120, "settable": True}) == [60, 90, 120]
    assert choices.refresh_choices({"min": 40, "max": 60}) == [40, 60]
    assert choices.refresh_choices({"min": 60, "max": 120, "settable": False}) == []
    assert choices.refresh_choices(None) == []


def test_fan_choices_need_a_real_choice():
    presets = [{"id": "silent"}, {"id": "balanced"}, {"id": "custom"}]
    assert choices.fan_choices({"supported": True, "presets": presets}) == ["auto", "silent", "balanced"]
    assert choices.fan_choices({"supported": True, "presets": []}) == []
    assert choices.fan_choices({"supported": False, "presets": presets}) == []


def test_level_caption_reads_the_published_clocks():
    freqs = {"6": {"cpu_khz": [2016000, 2803200], "gpu_mhz": 680}}
    assert choices.level_caption(freqs, 6, decimal_comma=True) == "2,8 GHz · 680 MHz"
    assert choices.level_caption(freqs, 6, decimal_comma=False) == "2.8 GHz · 680 MHz"
    assert choices.level_caption(freqs, 3, decimal_comma=True) == ""
    assert choices.level_caption(None, 6, decimal_comma=True) == ""


def test_step_at_ignores_the_dead_edges():
    assert choices.step_at(0, 222, 11, 1, 10) == 1
    assert choices.step_at(222, 222, 11, 1, 10) == 10
    assert choices.step_at(111, 222, 11, 1, 10) == 6


def test_lights_modes_follow_colores_capabilities():
    assert lights.modes({"color": True, "zones": 2, "batteryMode": True, "ambilight": True}) == [
        "solid", "gradient", "effect", "battery", "ambient"]
    assert lights.modes({"color": True}) == ["solid", "effect"]
    assert lights.modes({"color": False}) == []
    assert lights.effects({"supportedEffects": ["wave", "breathing"]}) == ["breathing", "wave"]
    assert lights.effects({}) == list(lights.COLORES_EFFECTS)


def test_lights_target_the_profile_that_is_lit():
    game = {"profileContext": {"scope": "game", "appKey": "894020", "followsGlobal": False}}
    assert lights.target(game) == ("game", "894020")
    assert lights.target({"profileContext": {"scope": "game", "appKey": "894020", "followsGlobal": True}}) == ("global", None)
    assert lights.target({}) == ("global", None)


def test_lights_swatch_shows_what_the_leds_show():
    red, blue = {"r": 255, "g": 0, "b": 0}, {"r": 0, "g": 0, "b": 255}
    base = {"power": True, "color": red, "gradient": [red, blue], "effect": {"id": "rainbow", "useGradient": False}}
    assert lights.swatch({**base, "mode": "solid"}) == ((255, 0, 0),)
    assert lights.swatch({**base, "mode": "gradient"}) == ((255, 0, 0), (0, 0, 255))
    assert lights.swatch({**base, "mode": "effect"}) == lights.SPECTRUM
    assert lights.swatch({**base, "mode": "effect", "effect": {"id": "breathing"}}) == ((255, 0, 0),)
    assert lights.swatch({**base, "power": False, "mode": "solid"}) is None


def test_bundled_font_config_is_valid_xml_for_any_plugin_folder(tmp_path, monkeypatch):
    import xml.etree.ElementTree as ET

    import app

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FONTCONFIG_FILE", raising=False)
    app._use_bundled_font("/home/deck/plugins/R&D <Panel>/dist/kiosk")
    tree = ET.parse(os.environ["FONTCONFIG_FILE"])
    assert tree.find("dir").text == "/home/deck/plugins/R&D <Panel>/dist/kiosk"


def test_an_unavailable_bottom_screen_says_why(monkeypatch, capsys):
    import app

    monkeypatch.delenv("PDC_KIOSK_URL", raising=False)
    assert app.main(["app.py", "/assets"]) == app.UNAVAILABLE
    assert "PDC_KIOSK_URL" in capsys.readouterr().err
