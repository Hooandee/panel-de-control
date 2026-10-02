import asyncio

from kiosk.controller import KioskController, RETRY_MAX_S
from kiosk.displays import Detection, SecondaryDisplay
from user_session import UserSession

DISPLAY = SecondaryDisplay("armada-lease", "DSI-1", "bottom_touchscreen", UserSession(1000, "/run/user/1000", "armada"))


class FakeServer:
    def __init__(self, *_args, on_error=None):
        self.port = None
        self.starts = 0

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/?k=t" if self.port else None

    async def start(self):
        self.starts += 1
        self.port = 4000

    async def stop(self):
        self.port = None


class FakeLauncher:
    def __init__(self, display, active=False, start_ok=True):
        self.display = display
        self.active = active
        self.start_ok = start_ok
        self.started_with = []
        self.stops = 0

    def is_active(self):
        return self.active

    def start(self, url):
        self.started_with.append(url)
        if self.start_ok:
            self.active = True
        return self.start_ok, "" if self.start_ok else "boom"

    def stop(self):
        self.stops += 1
        self.active = False
        return True, ""


def _controller(detections, launcher_kwargs=None, enabled=True, now=None):
    journal = []
    launchers = []
    clock = now or [0.0]

    def factory(display):
        launcher = FakeLauncher(display, **(launcher_kwargs or {}))
        launchers.append(launcher)
        return launcher

    controller = KioskController(
        "/static",
        dispatch=None,
        allowed_methods=(),
        journal=lambda level, event, **fields: journal.append((level, event, fields)),
        enabled=enabled,
        detect=lambda: detections[0] if len(detections) == 1 else detections.pop(0),
        launcher_factory=factory,
        server_factory=FakeServer,
        clock=lambda: clock[0],
    )
    return controller, launchers, journal, clock


def test_enabled_with_a_display_serves_and_launches():
    controller, launchers, journal, _ = _controller([Detection(DISPLAY, "ok")])
    asyncio.run(controller.tick())
    assert launchers[0].started_with == ["http://127.0.0.1:4000/?k=t"]
    assert controller.state()["available"] is True
    assert ("INFO", "launched", {"mechanism": "armada-lease"}) in journal


def test_disabled_never_starts_the_server_or_browser():
    controller, launchers, _, _ = _controller([Detection(DISPLAY, "ok")], enabled=False)
    asyncio.run(controller.tick())
    assert launchers == []
    assert controller._server.port is None


def test_leaving_game_mode_stops_the_browser_and_server():
    controller, launchers, journal, _ = _controller([Detection(DISPLAY, "ok"), Detection(None, "not_in_game_mode")])
    asyncio.run(controller.tick())
    asyncio.run(controller.tick())
    assert launchers[0].stops == 1
    assert controller._server.port is None
    state = controller.state()
    assert (state["supported"], state["available"], state["reason"]) == (True, False, "not_in_game_mode")


def test_machines_without_a_second_screen_are_unsupported():
    controller, _, _, _ = _controller([Detection(None, "no_secondary_display")])
    asyncio.run(controller.tick())
    assert controller.state()["supported"] is False


def test_failed_launches_back_off_and_are_journaled():
    clock = [0.0]
    controller, launchers, journal, _ = _controller(
        [Detection(DISPLAY, "ok")], launcher_kwargs={"start_ok": False}, now=clock,
    )
    asyncio.run(controller.tick())
    asyncio.run(controller.tick())
    assert len(launchers[0].started_with) == 1
    clock[0] = 5.0
    asyncio.run(controller.tick())
    assert len(launchers[0].started_with) == 2
    for _ in range(10):
        clock[0] += RETRY_MAX_S
        asyncio.run(controller.tick())
    assert controller._retry_delay == RETRY_MAX_S
    assert controller.state()["last_error"] == "boom"
    assert ("WARNING", "launch_failed", {"detail": "boom"}) in journal


def test_a_crashed_browser_is_relaunched():
    controller, launchers, _, clock = _controller([Detection(DISPLAY, "ok")])
    asyncio.run(controller.tick())
    launchers[0].active = False
    clock[0] = 10.0
    asyncio.run(controller.tick())
    assert len(launchers[0].started_with) == 2


def test_disabling_tears_everything_down():
    controller, launchers, journal, _ = _controller([Detection(DISPLAY, "ok")])
    asyncio.run(controller.tick())
    state = asyncio.run(controller.set_enabled(False))
    assert launchers[0].stops == 1
    assert state["enabled"] is False and state["running"] is False
    assert ("INFO", "disabled", {}) in journal


def test_refresh_reports_availability_without_launching():
    controller, launchers, _, _ = _controller([Detection(DISPLAY, "ok")], enabled=False)
    state = asyncio.run(controller.refresh())
    assert (state["supported"], state["available"], state["running"]) == (True, True, False)
    assert launchers == []
