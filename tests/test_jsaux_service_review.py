"""Regressions from the branch review: writes must stay rare even when things go wrong."""


from accessories.jsaux_pixel import codec, service
from accessories.jsaux_pixel.governor import _AUTOMATIC_PER_HOUR, Decision, Governor
from accessories.jsaux_pixel.render.canvas import Canvas
from accessories.jsaux_pixel.scenes.base import SceneContext, Segment
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


class WarmingUp(Steady):
    id = "warming"
    SETTLE = True

    def __init__(self):
        self.calls = 0

    def key(self, ctx):
        self.calls += 1
        return "--" if self.calls == 1 else "42"


class NotReady(Steady):
    id = "notready"

    def __init__(self):
        self.ready = False

    def key(self, ctx):
        return self.ready

    def render(self, ctx):
        segment = super().render(ctx)
        segment.ready = self.ready
        return segment


def test_a_reading_that_settles_after_one_tick_is_written_once(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = service.PixelService(
        store_path=tmp_path / "s.json", find_panel=panel.find, open_link=lambda port: FakeLink(panel),
        port_holders=lambda dev: [], clock=clock, log=lambda *a, **k: None, scenes={"warming": WarmingUp()},
        context=lambda now: SceneContext(now=now), handshake=lambda link: True, sleep=lambda s: None,
    )
    svc.set_scene("warming", {})
    for _ in range(5):
        svc.tick()
        clock.t += 1
    assert len(panel.commands(codec.Cmd.GIF_END)) == 1


def test_a_scene_that_is_not_ready_waits_without_writing(tmp_path):
    panel, clock = FakePanel(), Clock()
    scene = NotReady()
    svc = service.PixelService(
        store_path=tmp_path / "s.json", find_panel=panel.find, open_link=lambda port: FakeLink(panel),
        port_holders=lambda dev: [], clock=clock, log=lambda *a, **k: None, scenes={"notready": scene},
        context=lambda now: SceneContext(now=now), handshake=lambda link: True, sleep=lambda s: None,
    )
    svc.set_scene("notready", {})
    for _ in range(4):
        svc.tick()
        clock.t += 1
    assert panel.uploads() == []
    scene.ready = True
    for _ in range(3):
        svc.tick()
        clock.t += 1
    assert len(panel.commands(codec.Cmd.GIF_END)) == 1


def test_previews_do_not_move_the_live_scenes_steps(tmp_path):
    from accessories.jsaux_pixel.scenes import performance
    panel, clock = FakePanel(), Clock()
    heart = performance.HeartScene()
    readings = {"fps": 60}
    svc = service.PixelService(
        store_path=tmp_path / "s.json", find_panel=panel.find, open_link=lambda port: FakeLink(panel),
        port_holders=lambda dev: [], clock=clock, log=lambda *a, **k: None, scenes={"game_heart": heart},
        context=lambda now: SceneContext(now=now, metrics=dict(readings)), handshake=lambda link: True,
        sleep=lambda s: None,
    )
    svc.set_scene("game_heart", {})
    for _ in range(3):
        svc.tick()
        clock.t += 1
    readings["fps"] = 140
    svc.preview("game_heart", {})
    assert heart._fps.shown == 60


class Banner(Steady):
    id = "banner"

    def key(self, ctx):
        return ctx.options["alert"]["title"]

    def render(self, ctx):
        c = Canvas()
        c.px(int(ctx.options["alert"]["title"]) % 64, 5, (0, 0, 255))
        return Segment([c], [100])


def test_a_replugged_panel_gets_its_scene_back_even_when_nothing_is_written(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock)
    svc.set_scene("steady", {})
    svc.tick()
    panel.session = "7-1:7:9"
    for _ in range(4):
        clock.t += 6
        svc.tick()
    assert len(panel.commands(codec.Cmd.GIF_END)) == 2
    assert svc.state()["present"] is True


def test_resume_after_a_dark_suspend_rewrites_the_scene_once(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock)
    svc.set_scene("steady", {})
    svc.tick()
    svc.suspend(lambda: Segment([Canvas()], [100]))
    svc.resume()
    for _ in range(3):
        clock.t += 1
        svc.tick()
    assert len(panel.commands(codec.Cmd.GIF_END)) == 2


def test_an_achievement_burst_coalesces_and_the_scene_always_comes_back(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock)
    svc._scenes["banner"] = Banner()
    svc.set_scene("steady", {})
    svc.tick()
    for i in range(60):
        svc.show_alert("banner", {"title": str(i)}, seconds=20)
        clock.t += 1
        svc.tick()
    assert len(panel.commands(codec.Cmd.GIF_END)) <= 1 + 4
    assert svc.state()["showing"] == "banner"
    for n in range(_AUTOMATIC_PER_HOUR):
        svc._governor.record(f"filler{n}", ok=True, kind="scheduled")
    for _ in range(25):
        clock.t += 1
        svc.tick()
    assert svc.state()["showing"] == "steady"


def test_a_scene_chosen_before_the_game_settles_is_kept_for_that_game_only(tmp_path):
    panel, clock = FakePanel(), Clock()
    game = {"value": None}
    svc = _svc(tmp_path, panel, clock, game=game)
    svc.set_scene("steady", {})
    svc.set_game_scene("hourly")
    svc.tick()
    game["value"] = {"appid": "1"}
    svc.tick()
    svc.set_scene("steady", {"colour": 2})
    for _ in range(4):
        clock.t += 5
        svc.tick()
    assert svc.state()["showing"] == "steady"
    game["value"] = {"appid": "2"}
    for _ in range(4):
        clock.t += 6
        svc.tick()
    assert svc.state()["showing"] == "hourly"


def test_the_game_is_followed_while_the_screen_is_off(tmp_path):
    panel, clock = FakePanel(), Clock()
    game = {"value": {"appid": "1"}}
    svc = _svc(tmp_path, panel, clock, game=game)
    svc.set_scene("steady", {})
    svc.set_game_scene("hourly")
    svc.tick()
    svc.set_scene("steady", {"colour": 2})
    svc.set_power(False)
    game["value"] = None
    for _ in range(3):
        clock.t += 6
        svc.tick()
    assert svc._chosen_in is None


def test_a_pet_suspend_writes_nothing_while_the_screen_is_off(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock)
    svc.set_scene("steady", {})
    svc.set_on_suspend("pet")
    svc.tick()
    svc.set_power(False)
    clock.t += 1
    svc.tick()
    before = len(panel.commands(codec.Cmd.GIF_END))
    svc.suspend(lambda: Segment([Canvas()], [100]))
    assert len(panel.commands(codec.Cmd.GIF_END)) == before
    assert svc._rendered_key != ("suspend",)


class RefusesAnimation(FakeLink):
    refuse = True

    def request(self, data, timeout):
        if data[3] == codec.Cmd.ANIMATION and data[6] == 2 and RefusesAnimation.refuse:
            self.panel.sent.append(data)
            return None
        return super().request(data, timeout)


def test_a_refused_firmware_animation_is_retried(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock)
    svc._open_link = lambda port: RefusesAnimation(panel)
    svc.set_scene("fw", {})
    svc.tick()
    assert svc.state()["showing"] is None
    RefusesAnimation.refuse = False
    clock.t += 31
    svc.tick()
    assert svc.state()["showing"] == "fw"


class IgnoresPower(FakeLink):
    def request(self, data, timeout):
        if data[3] == codec.Cmd.POWER:
            self.panel.sent.append(data)
            return None
        return super().request(data, timeout)


def test_power_has_its_own_backoff(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock)
    svc._open_link = lambda port: IgnoresPower(panel)
    svc.set_scene("steady", {})
    for _ in range(120):
        svc.tick()
        clock.t += 1
    assert len(panel.commands(codec.Cmd.POWER)) <= 5


def test_turning_off_does_not_wait_for_the_upload_backoff(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock)
    svc.set_scene("steady", {})
    svc.tick()
    svc._retry_at = clock.t + 1800
    svc.set_power(False)
    clock.t += 1
    svc.tick()
    assert panel.commands(codec.Cmd.POWER)[-1] == codec.frame(1, codec.Cmd.POWER, b"\x00")


def test_night_follows_the_clock_zone_and_an_empty_window_is_no_night(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    panel, clock = FakePanel(), Clock()
    tokyo = ZoneInfo("Asia/Tokyo")
    svc = _svc(tmp_path, panel, clock, zone=lambda: tokyo)
    clock.t = datetime(2026, 10, 22, 23, 30, tzinfo=tokyo).timestamp()
    svc.set_night({"enabled": True, "from": "23:00", "to": "07:00"})
    assert svc.state()["night_active"] is True
    svc.set_night({"enabled": True, "from": "23:00", "to": "23:00"})
    assert svc.state()["night_active"] is False


def test_a_clock_set_backwards_does_not_block_writes_for_hours():
    clock = Clock()
    gov = Governor(clock)
    gov.record("a", ok=True, kind="scheduled")
    clock.t -= 3 * 3600
    assert gov.decide("b", "scheduled") is Decision.TOO_SOON
    assert gov.retry_in("scheduled") <= 20
    clock.t += 21
    assert gov.decide("b", "scheduled") is Decision.ALLOW


def test_a_replug_clears_an_old_failure_backoff(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock)
    svc.set_scene("steady", {})
    svc.tick()
    svc._retry_at, svc._failures = clock.t + 1800, 3
    panel.session = "7-1:7:9"
    for _ in range(4):
        clock.t += 6
        svc.tick()
    assert len(panel.commands(codec.Cmd.GIF_END)) == 2


def test_a_suspend_that_lands_after_the_wake_is_ignored(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock)
    svc.set_scene("steady", {})
    svc.tick()
    real_lock = svc._lock

    class LateLock:
        def __enter__(self):
            svc._lock = real_lock
            svc.resume()  # the wake wins the lock first
            return real_lock.__enter__()

        def __exit__(self, *exc):
            return real_lock.__exit__(*exc)

    clock.t += 1
    svc._lock = LateLock()
    svc.suspend(lambda: Segment([Canvas()], [100]))
    assert svc.state()["suspended"] is False


def test_a_game_scene_alone_connects_and_shows_while_playing(tmp_path):
    panel, clock, game = FakePanel(), Clock(), {"value": None}
    svc = _svc(tmp_path, panel, clock, game=game)
    svc.set_game_scene("steady", {})
    svc.tick()
    assert svc.state()["present"] is True
    assert panel.uploads() == []
    game["value"] = {"appid": "1"}
    for _ in range(15):
        clock.t += 1
        svc.tick()
    assert len(panel.uploads()) == 1


def test_an_alert_is_not_held_by_a_live_retry(tmp_path):
    panel, clock = FakePanel(), Clock()
    svc = _svc(tmp_path, panel, clock)
    svc.set_scene("steady", {})
    svc.tick()
    svc._retry_at = clock.t + 58
    svc.show_alert("steady", {"title": "x"})
    assert svc._retry_at == 0.0


def test_the_last_composition_is_remembered_after_another_scene(tmp_path):
    panel, clock = FakePanel(), Clock()
    scenes = {"composed": Steady(), "steady": Steady()}
    svc = service.PixelService(
        store_path=tmp_path / "s.json", find_panel=panel.find, open_link=lambda port: FakeLink(panel),
        port_holders=lambda dev: [], clock=clock, log=lambda *a, **k: None, scenes=scenes,
        context=lambda now: SceneContext(now=now), handshake=lambda link: True, official_active=lambda: False,
        sleep=lambda s: None,
    )
    layout = {"blocks": [{"type": "text", "x": 1, "y": 2, "text": "HI"}]}
    svc.set_scene("composed", {"layout": layout})
    svc.set_scene("steady", {})
    assert svc.state()["last_layout"] == layout
    again = service.PixelService(
        store_path=tmp_path / "s.json", find_panel=panel.find, open_link=lambda port: FakeLink(panel),
        port_holders=lambda dev: [], clock=clock, log=lambda *a, **k: None, scenes=scenes,
        context=lambda now: SceneContext(now=now), handshake=lambda link: True, official_active=lambda: False,
    )
    assert again.state()["last_layout"] == layout


def test_a_game_scene_alone_hands_the_panel_back_when_the_game_ends(tmp_path):
    panel, clock, game = FakePanel(), Clock(), {"value": {"appid": "1"}}
    svc = _svc(tmp_path, panel, clock, game=game)
    svc.set_game_scene("steady", {})
    for _ in range(15):
        clock.t += 1
        svc.tick()
    assert len(panel.uploads()) == 1
    game["value"] = None
    for _ in range(15):
        clock.t += 1
        svc.tick()
    assert len(panel.commands(codec.Cmd.ANIMATION)) == 1
    assert svc.state()["showing"] is None
