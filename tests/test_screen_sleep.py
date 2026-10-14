from display.screen_sleep import CONVAR, ScreenSleep


class FakeGamescope:
    """gamescope + kernel DRM: the convar switches every internal connector."""

    def __init__(self, tmp_path, connectors=("card0-eDP-1",), has_convar=True, lag=0, rc=0):
        self.drm = tmp_path / "drm"
        self.run_dir = tmp_path / "run" / "1000"
        self.run_dir.mkdir(parents=True)
        for name in ("gamescope-0", "gamescope-0-ei", "gamescope-0.lock", "gamescope-stats"):
            (self.run_dir / name).touch()
        self.nodes = []
        for name in connectors:
            node = self.drm / name
            node.mkdir(parents=True)
            (node / "dpms").write_text("On\n")
            self.nodes.append(node / "dpms")
        (self.drm / "card0-DP-1").mkdir()
        (self.drm / "card0-DP-1" / "dpms").write_text("Off\n")
        self.has_convar = has_convar
        self.lag = lag
        self.rc = rc
        self.calls = []
        self.pending = None

    def run(self, args, env):
        self.calls.append((args, env))
        if args[1] == "help":
            return 0, f"  {CONVAR}: Force the internal screen to be asleep\n" if self.has_convar else "x\n"
        if self.rc:
            return self.rc, ""
        self.pending = ("Off" if args[2] == "1" else "On", self.lag)
        self._advance()
        return 0, ""

    def _advance(self):
        if self.pending is None:
            return
        state, lag = self.pending
        if lag <= 0:
            for node in self.nodes:
                if node.read_text().strip() in ("On", "Off"):
                    node.write_text(state + "\n")
            self.pending = None
        else:
            self.pending = (state, lag - 1)

    def screen(self, **kw):
        now = [0.0]

        def sleep(s):
            now[0] += s
            self._advance()

        return ScreenSleep(runner=self.run, socket_glob=str(self.run_dir / "gamescope-*"),
                           drm_root=str(self.drm), clock=lambda: now[0], sleep=sleep, **kw)


def test_probe_finds_convar_and_uses_the_wayland_socket(tmp_path):
    gs = FakeGamescope(tmp_path)
    screen = gs.screen()
    assert screen.probe()
    args, env = gs.calls[0]
    assert args == ["gamescopectl", "help"]
    assert env == {"XDG_RUNTIME_DIR": str(gs.run_dir), "WAYLAND_DISPLAY": "gamescope-0"}


def test_probe_rejects_gamescope_without_convar(tmp_path):
    screen = FakeGamescope(tmp_path, has_convar=False).screen()
    assert not screen.probe()
    assert "convar missing" in screen.detail


def test_sleep_and_wake_are_confirmed_by_dpms(tmp_path):
    gs = FakeGamescope(tmp_path, lag=3)
    screen = gs.screen()
    screen.probe()
    assert screen.set(True)
    assert gs.nodes[0].read_text().strip() == "Off"
    assert gs.calls[-1][0] == ["gamescopectl", CONVAR, "1"]
    assert screen.set(False)
    assert gs.nodes[0].read_text().strip() == "On"
    assert gs.calls[-1][0] == ["gamescopectl", CONVAR, "0"]


def test_readback_that_never_changes_is_a_failure(tmp_path):
    gs = FakeGamescope(tmp_path, lag=10_000)
    screen = gs.screen()
    screen.probe()
    assert not screen.set(True)
    assert "readback" in screen.detail
    assert screen.asleep


def test_set_refuses_without_successful_probe(tmp_path):
    gs = FakeGamescope(tmp_path, has_convar=False)
    screen = gs.screen()
    screen.probe()
    assert not screen.set(True)
    assert all(args[1] == "help" for args, _ in gs.calls)


def test_gamescopectl_failure_is_reported(tmp_path):
    gs = FakeGamescope(tmp_path, rc=3)
    screen = gs.screen()
    screen.probe()
    assert not screen.set(True)
    assert screen.detail == "gamescopectl rc=3"


def test_internal_panel_already_off_is_not_slept(tmp_path):
    gs = FakeGamescope(tmp_path)
    gs.nodes[0].write_text("Off\n")
    screen = gs.screen()
    screen.probe()
    assert not screen.set(True)
    assert screen.detail == "no lit internal connector"


def test_wake_without_baseline_resets_convar_but_does_not_claim_success(tmp_path):
    gs = FakeGamescope(tmp_path)
    screen = gs.screen()
    screen.probe()
    assert not screen.set(False)
    assert gs.calls[-1][0] == ["gamescopectl", CONVAR, "0"]
    assert screen.detail == "woken without baseline"


def test_diagnostics_report_gamescope_version_and_connectors(tmp_path):
    gs = FakeGamescope(tmp_path)
    original = gs.run

    def run(args, env):
        if args[1] == "version":
            return 0, "gamescopectl version 3.16.23.4 (gcc 15.1.1)\nmore\n"
        return original(args, env)

    gs.run = run
    diag = gs.screen().diagnostics()
    assert diag["supported"] is True
    assert diag["gamescope_version"] == "gamescopectl version 3.16.23.4 (gcc 15.1.1)"
    assert list(diag["connectors"].values()) == ["On"]


def test_failed_sleep_command_still_counts_as_asleep_so_wake_resets_it(tmp_path):
    gs = FakeGamescope(tmp_path, rc=1)
    screen = gs.screen()
    screen.probe()
    assert not screen.set(True)
    assert screen.asleep
    gs.rc = 0
    assert screen.set(False)
    assert gs.calls[-1][0] == ["gamescopectl", CONVAR, "0"]
