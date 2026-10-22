import json

import pytest

from accessories.jsaux_pixel import codec, detect, service, transport
from accessories.jsaux_pixel.render.canvas import Canvas
from accessories.jsaux_pixel.scenes.base import Scene, SceneContext, Segment


class Clock:
    def __init__(self):
        self.t = 1_700_000_000.0

    def __call__(self):
        return self.t


class FakeLink:
    def __init__(self, panel):
        self.panel = panel
        self.is_open = False

    def open(self):
        if self.panel.unplugged:
            raise transport.TransportError("gone")
        self.is_open = True

    def close(self):
        self.is_open = False

    def send(self, data):
        self.panel.sent.append(data)

    def request(self, data, timeout):
        if self.panel.fail_after is not None and len(self.panel.sent) >= self.panel.fail_after:
            self.panel.unplugged = True
            raise transport.TransportError("unplugged")
        self.panel.sent.append(data)
        status = b"\x00" if data[3] == codec.Cmd.ANIMATION and data[6] > 3 else b"\x01"
        return codec.frame(data[2], data[3], status)


class FakePanel:
    def __init__(self):
        self.sent, self.unplugged, self.fail_after, self.holders = [], False, None, []

    def find(self):
        return None if self.unplugged else detect.PanelPort("/dev/ttyUSB0", "7-1", True)

    def uploads(self):
        return [f for f in self.sent if f[3] == codec.Cmd.GIF_BEGIN]

    def commands(self, cmd):
        return [f for f in self.sent if f[3] == cmd]


class Steady(Scene):
    id = "steady"
    UPLOADS_PER_HOUR = 0

    def key(self, ctx):
        return ctx.options.get("colour", 1)

    def render(self, ctx):
        c = Canvas()
        c.rect(0, 0, 8, 8, (200, 0, 0) if ctx.options.get("colour", 1) == 1 else (0, 200, 0))
        return Segment([c], [100])


class Hourly(Scene):
    id = "hourly"
    UPLOADS_PER_HOUR = 1

    def key(self, ctx):
        return int(ctx.now // 3600)

    def render(self, ctx):
        c = Canvas()
        c.px(int(ctx.now // 3600) % 64, 0, (255, 255, 255))
        return Segment([c], [100], valid_until=(int(ctx.now // 3600) + 1) * 3600)


class Firmware(Scene):
    id = "fw"
    UPLOADS_PER_HOUR = 0

    def key(self, ctx):
        return "fw"

    def render(self, ctx):
        return Segment([], [], firmware_animation=2)


@pytest.fixture
def rig(tmp_path):
    panel, clock, logs = FakePanel(), Clock(), []

    def make(**kw):
        svc = service.PixelService(
            store_path=tmp_path / "pixel.json",
            find_panel=panel.find,
            open_link=lambda port: FakeLink(panel),
            port_holders=lambda dev: panel.holders,
            clock=clock,
            log=lambda level, message, **fields: logs.append((level, message, fields)),
            scenes={s.id: s for s in (Steady(), Hourly(), Firmware())},
            context=lambda now: SceneContext(now=now, options={}),
            handshake=kw.pop("handshake", lambda link: True),
            **kw,
        )
        return svc

    return panel, clock, logs, make


def test_unchanged_scene_uploads_once(rig):
    panel, clock, _, make = rig
    svc = make()
    svc.set_scene("steady", {})
    for _ in range(50):
        svc.tick()
        clock.t += 30
    assert len(panel.uploads()) == 1
    assert svc.state()["present"] is True


def test_scene_expiry_triggers_exactly_one_new_upload(rig):
    panel, clock, _, make = rig
    clock.t = 3600 * 1000 + 10
    svc = make()
    svc.set_scene("hourly", {})
    svc.tick()
    clock.t += 1800
    svc.tick()
    clock.t += 1800
    svc.tick()
    svc.tick()
    assert len(panel.uploads()) == 2


def test_restart_does_not_resend_what_the_panel_already_shows(rig):
    panel, clock, _, make = rig
    svc = make()
    svc.set_scene("steady", {})
    svc.tick()
    again = make()
    again.tick()
    assert len(panel.uploads()) == 1


def test_brightness_is_sent_capped_to_the_supply(rig):
    panel, _, _, make = rig
    svc = make()
    svc.set_scene("steady", {})
    svc.tick()
    svc.set_brightness(100)
    svc.tick()
    assert panel.commands(codec.Cmd.BRIGHTNESS)[-1] == codec.frame(1, codec.Cmd.BRIGHTNESS, bytes([80]))


def test_firmware_animations_never_upload_a_gif(rig):
    panel, _, _, make = rig
    svc = make()
    svc.set_scene("fw", {})
    svc.tick()
    svc.tick()
    assert panel.uploads() == []
    assert panel.commands(codec.Cmd.ANIMATION)[-1] == codec.frame(1, codec.Cmd.ANIMATION, b"\x02")
    assert len([f for f in panel.commands(codec.Cmd.ANIMATION) if f[6] == 2]) == 1


def test_unplug_mid_upload_logs_and_waits_for_the_panel_to_return(rig):
    panel, clock, logs, make = rig
    svc = make()
    svc.set_scene("steady", {})
    svc.tick()
    panel.fail_after = len(panel.sent) + 2
    svc.set_scene("steady", {"colour": 2})
    svc.tick()
    assert svc.state()["present"] is False
    assert any(m == "upload_failed" for _, m, _ in logs)
    sent = len(panel.sent)
    for _ in range(5):
        clock.t += 1
        svc.tick()
    assert len(panel.sent) == sent
    panel.unplugged, panel.fail_after = False, None
    clock.t += 10
    svc.tick()
    assert len(panel.commands(codec.Cmd.GIF_END)) == 2
    assert svc.state()["present"] is True


def test_port_held_by_another_app_is_left_alone(rig):
    panel, _, _, make = rig
    panel.holders = [(321, "jsaux-matrix-dae")]
    svc = make()
    svc.set_scene("steady", {})
    svc.tick()
    assert panel.sent == []
    assert svc.state()["busy_by"] == "jsaux-matrix-dae"


def test_disabled_service_never_touches_hardware(rig):
    panel, _, _, make = rig
    svc = make(enabled=False)
    svc.set_scene("steady", {})
    svc.tick()
    assert panel.sent == []
    assert svc.state()["present"] is False


def test_settings_persist(rig, tmp_path):
    _, _, _, make = rig
    svc = make()
    svc.set_scene("steady", {"colour": 2})
    svc.set_brightness(40)
    stored = json.loads((tmp_path / "pixel.json").read_text())
    assert stored["scene"] == {"id": "steady", "options": {"colour": 2}}
    assert stored["brightness"] == 40
    assert make().state()["scene"] == "steady"


def test_unknown_scene_is_rejected(rig):
    _, _, _, make = rig
    with pytest.raises(ValueError):
        make().set_scene("nope", {})


def test_worker_thread_ticks_until_stopped(rig):
    panel, _, _, make = rig
    svc = make()
    svc.set_scene("steady", {})
    worker = service.Worker(svc, interval=0.01)
    worker.start()
    for _ in range(200):
        if panel.uploads():
            break
        import time
        time.sleep(0.01)
    worker.stop()
    assert not worker.is_alive()
    assert len(panel.uploads()) == 1


def test_nothing_is_written_until_a_scene_is_chosen(rig):
    panel, clock, _, make = rig
    svc = make()
    for _ in range(3):
        svc.tick()
        clock.t += 10
    assert panel.sent == []
    assert svc.state()["scene"] is None
    assert svc.state()["present"] is False


def test_commands_without_reply_get_the_official_settle_gap(rig):
    panel, clock, _, make = rig
    sleeps = []
    svc = make(sleep=sleeps.append)
    svc.set_scene("steady", {})
    svc.tick()
    assert sleeps and all(s >= 0.02 for s in sleeps)
    assert len(sleeps) >= 2


def _local(hour, minute=0):
    from datetime import datetime
    return datetime(2026, 10, 22, hour, minute).timestamp()


def test_night_schedule_switches_the_screen_off_and_back(rig):
    panel, clock, _, make = rig
    svc = make()
    svc.set_scene("steady", {})
    svc.set_night({"enabled": True, "from": "23:00", "to": "07:30"})
    clock.t = _local(22, 59)
    svc.tick()
    clock.t = _local(23, 1)
    svc.tick()
    assert panel.commands(codec.Cmd.POWER)[-1] == codec.frame(1, codec.Cmd.POWER, b"\x00")
    assert svc.state()["night_active"] is True
    clock.t = _local(23, 30)
    svc.tick()
    offs = [f for f in panel.commands(codec.Cmd.POWER) if f[6] == 0]
    assert len(offs) == 1
    clock.t = _local(7, 31) + 86400
    svc.tick()
    assert panel.commands(codec.Cmd.POWER)[-1] == codec.frame(1, codec.Cmd.POWER, b"\x01")
    assert svc.state()["night_active"] is False


def test_night_schedule_never_turns_on_a_screen_the_user_switched_off(rig):
    panel, clock, _, make = rig
    svc = make()
    svc.set_scene("steady", {})
    svc.set_night({"enabled": True, "from": "23:00", "to": "07:00"})
    svc.set_power(False)
    clock.t = _local(7, 30)
    svc.tick()
    assert all(f[6] == 0 for f in panel.commands(codec.Cmd.POWER))


def test_invalid_night_schedule_is_rejected(rig):
    _, _, _, make = rig
    with pytest.raises(ValueError):
        make().set_night({"enabled": True, "from": "25:00", "to": "07:00"})


def test_game_scene_takes_over_while_playing_and_returns_after(rig, tmp_path):
    panel, clock, _, make = rig
    game = {"on": False}
    from accessories.jsaux_pixel import service as svc_module
    svc = svc_module.PixelService(
        store_path=tmp_path / "auto.json", find_panel=panel.find, open_link=lambda port: FakeLink(panel),
        port_holders=lambda dev: [], clock=clock, log=lambda *a, **k: None,
        scenes={s.id: s for s in (Steady(), Firmware())},
        context=lambda now: SceneContext(now=now, game={"appid": "1"} if game["on"] else None),
        handshake=lambda link: True, sleep=lambda s: None,
    )
    svc.set_scene("steady", {})
    svc.set_game_scene("fw")
    svc.tick()
    assert panel.uploads() and not panel.commands(codec.Cmd.ANIMATION)
    game["on"] = True
    clock.t += 30
    svc.tick()
    clock.t += 30
    svc.tick()
    assert panel.commands(codec.Cmd.ANIMATION)
    assert svc.state()["scene"] == "steady" and svc.state()["showing"] == "fw"
    game["on"] = False
    clock.t += 30
    svc.tick()
    clock.t += 30
    svc.tick()
    assert len(panel.commands(codec.Cmd.GIF_END)) == 2
    assert svc.state()["showing"] == "steady"


def test_game_scene_can_be_cleared(rig):
    _, _, _, make = rig
    svc = make()
    svc.set_game_scene(None)
    assert svc.state()["game_scene"] is None
    with pytest.raises(ValueError):
        svc.set_game_scene("nope")


def test_alert_interrupts_then_returns(rig, tmp_path):
    panel, clock, _, make = rig
    from accessories.jsaux_pixel import service as svc_module
    svc = svc_module.PixelService(
        store_path=tmp_path / "alert.json", find_panel=panel.find, open_link=lambda port: FakeLink(panel),
        port_holders=lambda dev: [], clock=clock, log=lambda *a, **k: None,
        scenes={s.id: s for s in (Steady(), Firmware())},
        context=lambda now: SceneContext(now=now), handshake=lambda link: True, sleep=lambda s: None,
    )
    svc.set_scene("steady", {})
    svc.tick()
    svc.show_alert("fw", {"kind": "x"}, seconds=20)
    svc.tick()
    assert svc.state()["showing"] == "fw"
    clock.t += 21
    svc.tick()
    assert svc.state()["showing"] == "steady"
    assert len(panel.commands(codec.Cmd.GIF_END)) == 2


def test_alerts_are_ignored_when_no_scene_is_chosen(rig):
    panel, _, _, make = rig
    svc = make()
    svc.show_alert("fw", {}, seconds=20)
    svc.tick()
    assert panel.commands(codec.Cmd.ANIMATION) == []


def _asleep():
    c = Canvas()
    c.rect(20, 20, 6, 6, (40, 40, 120))
    return Segment([c, Canvas()], [50, 50])


def test_suspend_turns_the_panel_off_and_resume_brings_it_back(rig):
    panel, clock, _, make = rig
    svc = make()
    svc.set_scene("steady", {})
    svc.tick()
    svc.suspend(_asleep)
    assert codec.frame(1, codec.Cmd.POWER, b"\x00") in panel.sent
    uploads = len(panel.uploads())
    for _ in range(5):
        clock.t += 30
        svc.tick()
    assert len(panel.uploads()) == uploads
    assert panel.commands(codec.Cmd.POWER)[-1] == codec.frame(1, codec.Cmd.POWER, b"\x00")
    svc.resume()
    svc.tick()
    assert panel.commands(codec.Cmd.POWER)[-1] == codec.frame(1, codec.Cmd.POWER, b"\x01")
    assert svc.state()["suspended"] is False


def test_suspend_can_leave_the_pet_asleep_instead(rig):
    panel, clock, _, make = rig
    svc = make()
    svc.set_scene("steady", {})
    svc.set_on_suspend("pet")
    svc.tick()
    svc.suspend(_asleep)
    assert len(panel.uploads()) == 2
    assert codec.frame(1, codec.Cmd.POWER, b"\x00") not in panel.sent
    assert svc.state()["on_suspend"] == "pet"
    svc.resume()
    svc.tick()
    assert len(panel.uploads()) == 3


def test_suspend_choice_is_validated_and_kept(rig):
    _, _, _, make = rig
    svc = make()
    with pytest.raises(ValueError):
        svc.set_on_suspend("explode")
    svc.set_on_suspend("pet")
    assert make().state()["on_suspend"] == "pet"


def test_the_worker_notices_a_resume_by_the_clock_jump():
    calls = []

    class Svc:
        def tick(self):
            calls.append("tick")

        def resume(self):
            calls.append("resume")

        def log(self, *a, **k):
            pass

    wall, mono = [1000.0], [50.0]
    worker = service.Worker(Svc(), wall=lambda: wall[0], monotonic=lambda: mono[0])
    worker.step()
    wall[0] += 2
    mono[0] += 2
    worker.step()
    wall[0] += 3600
    mono[0] += 2
    worker.step()
    assert calls.count("resume") == 1


def test_the_game_scene_keeps_its_own_options(rig):
    _, _, _, make = rig
    svc = make()
    svc.set_game_scene("steady", {"colour": 2})
    assert svc.state()["game_options"] == {"colour": 2}
    assert make().state()["game_options"] == {"colour": 2}
    svc.set_game_scene(None)
    assert svc.state()["game_options"] == {}


def test_a_suspend_that_never_happened_wears_off(rig):
    panel, clock, _, make = rig
    svc = make()
    svc.set_scene("steady", {})
    svc.tick()
    svc.suspend(_asleep)
    clock.t += 60
    svc.tick()
    assert svc.state()["suspended"] is True
    clock.t += 200
    svc.tick()
    assert svc.state()["suspended"] is False
    assert panel.commands(codec.Cmd.POWER)[-1] == codec.frame(1, codec.Cmd.POWER, b"\x01")


def test_refresh_rewrites_without_forgetting_what_is_shown(rig):
    panel, clock, _, make = rig
    svc = make()
    svc.set_scene("steady", {})
    svc.tick()
    svc.refresh()
    clock.t += 1
    svc.tick()
    assert len(panel.uploads()) == 1
