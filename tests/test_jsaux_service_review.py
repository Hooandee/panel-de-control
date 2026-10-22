"""Regressions from the branch review: writes must stay rare even when things go wrong."""

import pytest

from accessories.jsaux_pixel import codec, detect, service
from accessories.jsaux_pixel.governor import Decision, Governor
from accessories.jsaux_pixel.scenes.base import SceneContext
from test_jsaux_service import FakeLink, FakePanel, Firmware, Hourly, Steady


class Clock:
    def __init__(self):
        self.t = 1_700_000_000.0

    def __call__(self):
        return self.t


def _svc(tmp_path, panel, clock, logs=None, game=None, handshake=lambda link: True, official=lambda: False, **kw):
    return service.PixelService(
        store_path=tmp_path / "s.json", find_panel=panel.find, open_link=lambda port: FakeLink(panel),
        port_holders=lambda dev: panel.holders, clock=clock,
        log=lambda level, message, **fields: (logs if logs is not None else []).append(message),
        scenes={s.id: s for s in (Steady(), Hourly(), Firmware())},
        context=lambda now: SceneContext(now=now, game=(game or {}).get("value")),
        handshake=handshake, official_active=official, sleep=lambda s: None, **kw,
    )


class NakEnd(FakeLink):
    def request(self, data, timeout):
        if data[3] == codec.Cmd.GIF_END:
            self.panel.sent.append(data)
            return None
        return super().request(data, timeout)


def test_failed_uploads_back_off_instead_of_retrying_every_second(tmp_path):
    panel, clock, logs = FakePanel(), Clock(), []
    svc = service.PixelService(
        store_path=tmp_path / "s.json", find_panel=panel.find, open_link=lambda port: NakEnd(panel),
        port_holders=lambda dev: [], clock=clock, log=lambda level, message, **f: logs.append(message),
        scenes={"steady": Steady()}, context=lambda now: SceneContext(now=now), handshake=lambda link: True,
        official_active=lambda: False, sleep=lambda s: None,
    )
    svc.set_scene("steady", {})
    for _ in range(3600):
        svc.tick()
        clock.t += 1
    assert len(panel.commands(codec.Cmd.GIF_END)) <= 8
    assert logs.count("nak") <= 8


def test_gifs_over_the_size_limit_are_never_sent(tmp_path, monkeypatch):
    monkeypatch.setattr(codec, "MAX_GIF_BYTES", 10)
    panel, clock, logs = FakePanel(), Clock(), []
    svc = _svc(tmp_path, panel, clock, logs)
    svc.set_scene("steady", {})
    for _ in range(30):
        svc.tick()
        clock.t += 1
    assert panel.uploads() == []
    assert logs.count("too_large") == 1


def test_end_timeout_grows_with_the_gif():
    assert service.end_timeout(64 * 1024) > 2.0
    assert service.end_timeout(500) >= 1.0


def test_nothing_touches_the_port_until_a_scene_is_chosen(tmp_path):
    panel, clock = FakePanel(), Clock()
    opened = []
    svc = service.PixelService(
        store_path=tmp_path / "s.json", find_panel=panel.find, open_link=lambda port: opened.append(port) or FakeLink(panel),
        port_holders=lambda dev: [], clock=clock, log=lambda *a, **k: None, scenes={"steady": Steady()},
        context=lambda now: SceneContext(now=now), handshake=lambda link: True, official_active=lambda: False,
    )
    for _ in range(10):
        svc.tick()
        clock.t += 10
    assert opened == [] and panel.sent == []


def test_official_app_service_keeps_panel_away_even_without_an_open_fd(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock, official=lambda: True)
    svc.set_scene("steady", {})
    svc.tick()
    assert panel.sent == []
    assert svc.state()["busy_by"] == "jsaux"


def test_a_device_that_fails_the_handshake_is_left_alone(tmp_path):
    panel, clock, logs = FakePanel(), Clock(), []
    svc = _svc(tmp_path, panel, clock, logs, handshake=lambda link: False)
    svc.set_scene("steady", {})
    for _ in range(30):
        svc.tick()
        clock.t += 1
    assert panel.sent == []
    assert logs.count("not_a_panel") == 1
    assert svc.state()["present"] is False


def test_game_and_alert_transitions_are_not_user_writes(tmp_path):
    panel, clock = FakePanel(), Clock()
    game = {"value": None}
    svc = _svc(tmp_path, panel, clock, game=game)
    svc.set_scene("steady", {})
    svc.set_game_scene("fw")
    svc.tick()
    kinds = []
    real = svc._governor.record
    svc._governor.record = lambda h, ok, kind="user", metric=None: (kinds.append(kind), real(h, ok, kind, metric))
    game["value"] = {"appid": "1"}
    for _ in range(15):
        clock.t += 1
        svc.tick()
    assert kinds and "user" not in kinds


def test_a_game_flapping_on_and_off_does_not_switch_scenes(tmp_path):
    panel, clock = FakePanel(), Clock()
    game = {"value": None}
    svc = _svc(tmp_path, panel, clock, game=game)
    svc.set_scene("steady", {})
    svc.set_game_scene("fw")
    svc.tick()
    for i in range(8):
        game["value"] = {"appid": "1"} if i % 2 == 0 else None
        clock.t += 1
        svc.tick()
    assert panel.commands(codec.Cmd.ANIMATION) == []


def test_nothing_is_uploaded_while_the_screen_is_off(tmp_path):
    panel, clock = FakePanel(), Clock()
    clock.t = 3600 * 1000 + 10
    svc = _svc(tmp_path, panel, clock)
    svc.set_scene("hourly", {})
    svc.tick()
    svc.set_power(False)
    clock.t += 1
    svc.tick()
    before = len(panel.commands(codec.Cmd.GIF_END))
    for _ in range(3):
        clock.t += 3600
        svc.tick()
    assert len(panel.commands(codec.Cmd.GIF_END)) == before
    svc.set_power(True)
    clock.t += 1
    svc.tick()
    assert len(panel.commands(codec.Cmd.GIF_END)) == before + 1


def test_after_another_app_held_the_port_the_scene_is_sent_again(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock)
    svc.set_scene("steady", {})
    svc.tick()
    svc.stop()
    panel.holders = [(5, "jsaux-matrix-dae")]
    clock.t += 10
    svc.tick()
    panel.holders = []
    clock.t += 31
    svc.tick()
    assert len(panel.commands(codec.Cmd.GIF_END)) == 2


def test_refusals_are_logged_once_and_not_rerendered_every_tick(tmp_path):
    panel, clock, logs = FakePanel(), Clock(), []
    svc = _svc(tmp_path, panel, clock, logs)
    renders = []
    steady = svc._scenes["steady"]
    original = steady.render
    steady.render = lambda ctx: renders.append(1) or original(ctx)
    svc.set_scene("steady", {})
    svc.tick()
    svc._governor = Governor(clock)
    for _ in range(60):
        svc._governor.decide = lambda *a, **k: Decision.BUDGET
        svc._rendered_key = None
        clock.t += 1
        svc.tick()
    assert logs.count("skipped") <= 2
    assert len(renders) <= 4


def test_hour_boundary_upload_is_not_blocked_by_the_live_budget():
    clock = Clock()
    gov = Governor(clock)
    for n in range(60):
        gov.record(f"x{n}", ok=True, kind="scheduled")
        clock.t += 21
    assert gov.decide("next", "scheduled") is Decision.BUDGET
    assert gov.decide("boundary", "boundary") is Decision.ALLOW
