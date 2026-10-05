import subprocess
import sys

from kiosk import displays
from kiosk.displays import Detection, SecondaryDisplay, detect, parse_device_env
from kiosk.launcher import KioskLauncher, UNIT, launch_argv
from user_session import UserSession

THOR_ENV = """ARMADA_DEVICE_ID=ayn-thor
ARMADA_SECONDARY_BACKLIGHT=ae94000.dsi.0
ARMADA_DEVICE_NAME=AYN\\ Thor
ARMADA_SECONDARY_CONNECTOR=DSI-1
ARMADA_SECONDARY_TOUCHSCREEN=bottom_touchscreen
ARMADA_GAMESCOPE_FAKE_OUTPUT_MM=''
"""

SESSION = UserSession(1000, "/run/user/1000", "armada")


def _exists(*present):
    return lambda path: path in present


ALL_PRESENT = (displays.ARMADA_RUN_BOTTOM, displays.SYSTEM_PYTHON, displays.ARMADA_LEASE_SOCKET)


def test_parses_armada_device_env_shell_quoting():
    env = parse_device_env(THOR_ENV)
    assert env["ARMADA_DEVICE_NAME"] == "AYN Thor"
    assert env["ARMADA_SECONDARY_CONNECTOR"] == "DSI-1"
    assert env["ARMADA_GAMESCOPE_FAKE_OUTPUT_MM"] == ""


def test_thor_in_game_mode_has_a_secondary_display(monkeypatch):
    monkeypatch.setattr(displays, "session_for_uid", lambda uid: SESSION if uid == 1000 else None)
    found = detect(exists=_exists(*ALL_PRESENT), owner_uid=lambda _p: 1000, run=lambda _a: THOR_ENV)
    assert found == Detection(SecondaryDisplay("armada-lease", "DSI-1", "bottom_touchscreen", SESSION, "ae94000.dsi.0"), "ok")


def test_every_missing_piece_has_its_own_reason(monkeypatch):
    monkeypatch.setattr(displays, "session_for_uid", lambda uid: SESSION)
    single = THOR_ENV.replace("ARMADA_SECONDARY_CONNECTOR=DSI-1\n", "")
    cases = [
        (_exists(), THOR_ENV, "no_mechanism"),
        (_exists(*ALL_PRESENT), single, "no_secondary_display"),
        (_exists(displays.ARMADA_RUN_BOTTOM, displays.ARMADA_LEASE_SOCKET), THOR_ENV, "no_runtime"),
        (_exists(displays.ARMADA_RUN_BOTTOM, displays.SYSTEM_PYTHON), THOR_ENV, "not_in_game_mode"),
    ]
    for exists, env, reason in cases:
        found = detect(exists=exists, owner_uid=lambda _p: 1000, run=lambda _a, env=env: env)
        assert found == Detection(None, reason)


def test_unknown_lease_owner_is_not_guessed(monkeypatch):
    monkeypatch.setattr(displays, "session_for_uid", lambda uid: None)
    found = detect(exists=_exists(*ALL_PRESENT), owner_uid=lambda _p: 4242, run=lambda _a: THOR_ENV)
    assert found == Detection(None, "no_session")


def test_bottom_screen_is_the_native_app_with_the_url_from_the_unit_env(tmp_path):
    log = tmp_path / "log"
    native = tmp_path / "Panel de Control" / "app.py"
    native.parent.mkdir()
    native.write_text(
        "import os, sys\n"
        f"open({str(log)!r}, 'w').write(os.environ['PDC_KIOSK_URL'] + ' ' + ' '.join(sys.argv[1:]))\n"
    )
    argv = launch_argv(native=str(native), assets="/assets dir")
    assert argv[0] == "/usr/bin/python3" and not any("?k=" in part for part in argv)
    env = {"PDC_KIOSK_URL": "http://127.0.0.1:1/?k=t", "PATH": "/usr/bin:/bin"}
    assert subprocess.run([sys.executable, *argv[1:]], env=env, check=False, timeout=20).returncode == 0
    assert log.read_text() == "http://127.0.0.1:1/?k=t /assets dir"


def _launcher(results):
    calls = []

    def runner(cmd, env, identity):
        calls.append((cmd, env, identity))
        return results.pop(0) if results else (0, "")

    display = SecondaryDisplay("armada-lease", "DSI-1", "bottom_touchscreen", SESSION)
    return KioskLauncher(display, runner=runner), calls


def test_start_runs_a_transient_user_unit_in_the_session():
    launcher, calls = _launcher([(0, ""), (0, "")])
    ok, _ = launcher.start("http://127.0.0.1:4000/?k=t")
    assert ok
    cmd, env, _identity = calls[1]
    assert cmd[0].endswith("systemd-run")
    assert f"--unit={UNIT}" in cmd
    assert "--setenv=PDC_KIOSK_URL=http://127.0.0.1:4000/?k=t" in cmd
    assert "--nice=10" in cmd and "--property=CPUWeight=20" in cmd
    assert env["XDG_RUNTIME_DIR"] == "/run/user/1000"


def test_last_words_come_from_the_unit_journal_since_this_launch():
    launcher, calls = _launcher([(0, ""), (0, ""), (0, "Traceback\npdc-kiosk native: no_lease_fd")])
    assert launcher.last_words() == ""
    launcher.start("http://127.0.0.1:1/?k=t")
    assert launcher.last_words().endswith("no_lease_fd")
    cmd = calls[-1][0]
    assert f"_SYSTEMD_USER_UNIT={UNIT}.service" in cmd
    assert any(part.startswith("--since=@") for part in cmd)


def test_is_active_requires_the_exact_state():
    launcher, _ = _launcher([(0, "active")])
    assert launcher.is_active()
    launcher, _ = _launcher([(3, "failed")])
    assert not launcher.is_active()
    launcher, _ = _launcher([(0, "activating")])
    assert not launcher.is_active()


def test_failed_start_is_reported():
    launcher, _ = _launcher([(0, ""), (1, "Unit pdc-kiosk.service already exists")])
    ok, detail = launcher.start("http://127.0.0.1:1/?k=t")
    assert not ok
    assert "already exists" in detail


def test_backlight_power_writes_blank_codes_and_refuses_paths(tmp_path):
    from kiosk.displays import set_backlight_power

    (tmp_path / "ae94000.dsi.0").mkdir()
    assert set_backlight_power("ae94000.dsi.0", False, sys_root=str(tmp_path))
    assert (tmp_path / "ae94000.dsi.0" / "bl_power").read_text() == "4"
    assert set_backlight_power("ae94000.dsi.0", True, sys_root=str(tmp_path))
    assert (tmp_path / "ae94000.dsi.0" / "bl_power").read_text() == "0"
    assert not set_backlight_power("../../etc", False, sys_root=str(tmp_path))
    assert not set_backlight_power("", False, sys_root=str(tmp_path))


def test_stop_does_not_wait_for_the_bottom_screen_to_exit():
    launcher, calls = _launcher([(0, "")])
    ok, _ = launcher.stop()
    assert ok
    assert [cmd[-3:] for cmd, _env, _identity in calls] == [["stop", "--no-block", UNIT]]
