"""Start, watch and stop the kiosk browser as a transient user unit in the game session."""

import os
import shlex
import subprocess
from typing import Callable

from kiosk.displays import ARMADA_RUN_BOTTOM, FIREFOX, SecondaryDisplay
from user_session import spawn_args

UNIT = "pdc-kiosk"
PROFILE_DIR = "$HOME/.cache/panel-de-control/kiosk"
SYSTEM_PYTHON = "/usr/bin/python3"
WEBVIEW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webview.py")


# Fresh kiosk profile: no first-run pages, restore prompts or default-browser nags.
FIREFOX_PREFS = (
    'user_pref("browser.shell.checkDefaultBrowser", false);',
    'user_pref("browser.startup.homepage_override.mstone", "ignore");',
    'user_pref("browser.aboutwelcome.enabled", false);',
    'user_pref("browser.sessionstore.resume_from_crash", false);',
    'user_pref("datareporting.policy.dataSubmissionEnabled", false);',
    'user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);',
    'user_pref("app.update.enabled", false);',
    # One local page: a single content process and nothing in the background, so the bottom
    # screen stays small next to a game that already fills the memory of the handheld.
    'user_pref("fission.autostart", false);',
    'user_pref("dom.ipc.processCount", 1);',
    'user_pref("dom.ipc.processCount.webIsolated", 1);',
    'user_pref("dom.ipc.processPrelaunch.enabled", false);',
    'user_pref("dom.ipc.keepProcessesAlive.web", 0);',
    'user_pref("extensions.webextensions.remote", false);',
    'user_pref("browser.tabs.remote.separatePrivilegedContentProcess", false);',
    'user_pref("browser.tabs.remote.separatePrivilegedMozillaWebContentProcess", false);',
    'user_pref("media.rdd-process.enabled", false);',
    'user_pref("browser.cache.memory.capacity", 8192);',
    'user_pref("image.mem.surfacecache.max_size_kb", 65536);',
    'user_pref("browser.sessionhistory.max_total_viewers", 0);',
    'user_pref("accessibility.force_disabled", 1);',
    'user_pref("browser.safebrowsing.malware.enabled", false);',
    'user_pref("browser.safebrowsing.phishing.enabled", false);',
    'user_pref("browser.safebrowsing.downloads.enabled", false);',
    'user_pref("browser.safebrowsing.blockedURIs.enabled", false);',
    'user_pref("network.captive-portal-service.enabled", false);',
    'user_pref("network.connectivity-service.enabled", false);',
    'user_pref("app.normandy.enabled", false);',
    'user_pref("toolkit.telemetry.enabled", false);',
    'user_pref("datareporting.healthreport.uploadEnabled", false);',
    'user_pref("extensions.update.enabled", false);',
    'user_pref("browser.search.update", false);',
)

# gamescope's nested Wayland crashes Firefox (nsWaylandDisplay::Init); X11 + XInput2 gives touch.
BROWSER_ENV = ("MOZ_ENABLE_WAYLAND=0", "GDK_BACKEND=x11", "MOZ_USE_XINPUT2=1")

Runner = Callable[[list[str], dict, dict], tuple[int, str]]


def _default_runner(cmd: list[str], env: dict, identity: dict) -> tuple[int, str]:
    try:
        done = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=10, check=False, **identity)
        return done.returncode, (done.stdout or done.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def launch_script(url_var: str = "PDC_KIOSK_URL", webview: str = WEBVIEW) -> str:
    """WebKitGTK first (a fraction of Firefox's memory next to a game); Firefox if it is missing or fails."""
    prefs = "\\n".join(FIREFOX_PREFS)
    inside = (
        f'{SYSTEM_PYTHON} {shlex.quote(webview)} "$0" && exit 0; '
        f'exec {FIREFOX} --kiosk --no-remote --profile "{PROFILE_DIR}" "$0"'
    )
    return (
        f'mkdir -p "{PROFILE_DIR}" && printf \'{prefs}\\n\' > "{PROFILE_DIR}/user.js" && '
        f"exec {ARMADA_RUN_BOTTOM} -- /usr/bin/env -u WAYLAND_DISPLAY {' '.join(BROWSER_ENV)} "
        f'/bin/sh -c {shlex.quote(inside)} "${url_var}"'
    )


NICE = 10
CPU_WEIGHT = 20


class KioskLauncher:
    def __init__(self, display: SecondaryDisplay, runner: Runner = _default_runner):
        self.display = display
        self.runner = runner

    def _systemd(self, argv: list[str]) -> tuple[int, str]:
        cmd, env, identity = spawn_args(self.display.session, argv)
        return self.runner(cmd, env, identity)

    def start(self, url: str) -> tuple[bool, str]:
        self._systemd(["systemctl", "--user", "reset-failed", UNIT])
        code, out = self._systemd([
            "systemd-run", "--user", f"--unit={UNIT}", "--collect", "--quiet",
            # The bottom screen must never take CPU time from the game on the top one.
            f"--nice={NICE}", f"--property=CPUWeight={CPU_WEIGHT}",
            f"--setenv=PDC_KIOSK_URL={url}",
            "/bin/sh", "-c", launch_script(),
        ])
        return code == 0, out

    def is_active(self) -> bool:
        code, out = self._systemd(["systemctl", "--user", "is-active", UNIT])
        return code == 0 and out == "active"

    def stop(self) -> tuple[bool, str]:
        # --no-block: Decky SIGKILLs a plugin that takes 5 s to unload, and a killed plugin
        # can leave the loader spinning. The transient unit is --collect, so nothing lingers.
        code, out = self._systemd(["systemctl", "--user", "stop", "--no-block", UNIT])
        return code == 0, out
