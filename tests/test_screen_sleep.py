from display.screen_sleep import CONVAR, ScreenSleep


class FakeGamescope:
    """gamescope + kernel DRM: the convar switches the internal connector after `lag` polls."""

    def __init__(self, tmp_path, has_convar=True, lag=0, rc=0):
        self.drm = tmp_path / "drm"
        for name, state in (("card0-eDP-1", "On"), ("card0-DP-1", "Off")):
            (self.drm / name).mkdir(parents=True)
            (self.drm / name / "dpms").write_text(state + "\n")
        self.panel = self.drm / "card0-eDP-1" / "dpms"
        self.has_convar, self.lag, self.rc = has_convar, lag, rc
        self.calls, self.pending = [], None

    def ctl(self, *args):
        self.calls.append(args)
        if args[0] == "help":
            return 0, f"{CONVAR}: Force the internal screen to be asleep" if self.has_convar else ""
        if args[0] == "version":
            return 0, "gamescopectl version 3.16.23.4\n"
        if self.rc:
            return self.rc, ""
        self.pending = ["Off" if args[1] == "1" else "On", self.lag]
        self.advance()
        return 0, ""

    def advance(self):
        if self.pending and self.pending[1] <= 0:
            self.panel.write_text(self.pending[0] + "\n")
            self.pending = None
        elif self.pending:
            self.pending[1] -= 1

    def screen(self):
        now = [0.0]

        def sleep(s):
            now[0] += s
            self.advance()

        screen = ScreenSleep(ctl=self.ctl, drm_root=str(self.drm), clock=lambda: now[0], sleep=sleep)
        screen.probe()
        return screen


def test_probe_needs_the_convar_and_clears_a_leftover_sleep(tmp_path):
    gs = FakeGamescope(tmp_path)
    screen = gs.screen()
    assert screen.supported and screen.version == "gamescopectl version 3.16.23.4"
    assert gs.calls[-1] == (CONVAR, "0")
    assert not FakeGamescope(tmp_path / "old", has_convar=False).screen().supported


def test_sleep_and_wake_wait_for_dpms_readback(tmp_path):
    gs = FakeGamescope(tmp_path, lag=3)
    screen = gs.screen()
    assert screen.set(True) and gs.panel.read_text().strip() == "Off"
    assert screen.set(False) and gs.panel.read_text().strip() == "On"


def test_readback_that_never_changes_fails_but_counts_as_asleep(tmp_path):
    screen = FakeGamescope(tmp_path, lag=10_000).screen()
    assert not screen.set(True)
    assert screen.asleep and "readback" in screen.detail


def test_failed_sleep_command_still_counts_as_asleep_so_wake_resets_it(tmp_path):
    gs = FakeGamescope(tmp_path, rc=1)
    screen = gs.screen()
    assert not screen.set(True) and screen.asleep
    gs.rc = 0
    assert screen.set(False)
    assert gs.calls[-1] == (CONVAR, "0")


def test_unsupported_or_unlit_panel_is_never_slept(tmp_path):
    assert not FakeGamescope(tmp_path, has_convar=False).screen().set(True)
    gs = FakeGamescope(tmp_path / "docked")
    docked = gs.screen()
    gs.panel.write_text("Off\n")
    assert not docked.set(True) and not docked.asleep


def test_close_wakes_the_panel_and_rejects_a_late_sleep(tmp_path):
    gs = FakeGamescope(tmp_path)
    screen = gs.screen()
    assert screen.set(True)

    assert screen.close() and gs.panel.read_text().strip() == "On"
    assert not screen.set(True)
    assert gs.panel.read_text().strip() == "On" and screen.detail == "closed"


def test_close_on_a_lit_panel_sends_nothing(tmp_path):
    gs = FakeGamescope(tmp_path)
    screen = gs.screen()
    sent = len(gs.calls)

    assert screen.close()
    assert len(gs.calls) == sent


def test_close_during_an_in_flight_sleep_leaves_the_panel_lit(tmp_path):
    gs = FakeGamescope(tmp_path, lag=3)
    screen = gs.screen()
    original_ctl = gs.ctl

    def ctl_then_close(*args):
        result = original_ctl(*args)
        if args == (CONVAR, "1"):
            screen.close()
        return result

    screen._ctl = ctl_then_close

    assert not screen.set(True)
    for _ in range(5):
        gs.advance()
    assert gs.calls[-1] == (CONVAR, "0")
    assert gs.panel.read_text().strip() == "On" and not screen.asleep
