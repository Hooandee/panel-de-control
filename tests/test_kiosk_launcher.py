import subprocess

from kiosk import displays
from kiosk.displays import Detection, SecondaryDisplay, detect, parse_device_env
from kiosk.launcher import KioskLauncher, UNIT, launch_script
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


ALL_PRESENT = (displays.ARMADA_RUN_BOTTOM, displays.FIREFOX, displays.ARMADA_LEASE_SOCKET)


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
        (_exists(displays.ARMADA_RUN_BOTTOM, displays.ARMADA_LEASE_SOCKET), THOR_ENV, "no_browser"),
        (_exists(displays.ARMADA_RUN_BOTTOM, displays.FIREFOX), THOR_ENV, "not_in_game_mode"),
    ]
    for exists, env, reason in cases:
        found = detect(exists=exists, owner_uid=lambda _p: 1000, run=lambda _a, env=env: env)
        assert found == Detection(None, reason)


def test_unknown_lease_owner_is_not_guessed(monkeypatch):
    monkeypatch.setattr(displays, "session_for_uid", lambda uid: None)
    found = detect(exists=_exists(*ALL_PRESENT), owner_uid=lambda _p: 4242, run=lambda _a: THOR_ENV)
    assert found == Detection(None, "no_session")


def test_launch_script_keeps_firefox_on_x11_with_touch():
    script = launch_script()
    assert "exec /usr/bin/armada-run-bottom -- /usr/bin/env -u WAYLAND_DISPLAY" in script
    assert "MOZ_ENABLE_WAYLAND=0 GDK_BACKEND=x11 MOZ_USE_XINPUT2=1" in script
    assert '--kiosk --no-remote --profile "$HOME/.cache/panel-de-control/kiosk" "$PDC_KIOSK_URL"' in script


def test_launch_script_is_valid_shell():
    assert subprocess.run(["sh", "-n", "-c", launch_script()], check=False).returncode == 0


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
    assert env["XDG_RUNTIME_DIR"] == "/run/user/1000"


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
