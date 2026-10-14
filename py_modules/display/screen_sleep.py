"""Internal panel power through gamescope's `drm_sleep_internal_screen` convar.

gamescope owns DRM master, so nothing else can switch the connector off. The convar
(gamescope >= 3.16.5) disables the internal connector; the kernel connector `dpms`
node is the readback.
"""

import glob
import os
import re
import subprocess
import time

CONVAR = "drm_sleep_internal_screen"
_INTERNAL_CONNECTORS = ("eDP", "DSI", "LVDS")
_SOCKET_NAME = re.compile(r"gamescope-\d+$")
_PROBE_RETRY_S = 30.0
_READBACK_TIMEOUT_S = 2.0
_READBACK_STEP_S = 0.1


def _run(args, env):
    try:
        from controllers.detect import clean_env, resolve_bin
        p = subprocess.run([resolve_bin(args[0]), *args[1:]], capture_output=True, text=True,
                           timeout=2, env={**clean_env(), **env})
        # `gamescopectl help` lists convars on stderr.
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _internal_dpms_paths(drm_root):
    paths = []
    for path in sorted(glob.glob(os.path.join(drm_root, "card*-*"))):
        connector = os.path.basename(path).split("-", 1)[1]
        if connector.startswith(_INTERNAL_CONNECTORS):
            paths.append(os.path.join(path, "dpms"))
    return paths


class ScreenSleep:
    """Blocking: call off the event loop. `runner(args, env) -> (rc, output)`."""

    def __init__(self, runner=_run, socket_glob="/run/user/*/gamescope-*",
                 drm_root="/sys/class/drm", clock=time.monotonic, sleep=time.sleep):
        self._run = runner
        self._socket_glob = socket_glob
        self._drm_root = drm_root
        self._clock = clock
        self._sleep = sleep
        self._supported = False
        self._last_probe = None
        self.detail = "not probed"
        self.asleep = False
        self._lit = []

    def _env(self):
        for sock in sorted(glob.glob(self._socket_glob)):
            if _SOCKET_NAME.match(os.path.basename(sock)):
                return {"XDG_RUNTIME_DIR": os.path.dirname(sock),
                        "WAYLAND_DISPLAY": os.path.basename(sock)}
        return None

    def _read_dpms(self, paths=None):
        states = {}
        for path in paths if paths is not None else _internal_dpms_paths(self._drm_root):
            try:
                with open(path) as f:
                    states[path] = f.read().strip()
            except OSError:
                continue
        return states

    @property
    def probe_ok(self):
        return self._supported

    def probe(self):
        if self._supported:
            return True
        now = self._clock()
        if self._last_probe is not None and now - self._last_probe < _PROBE_RETRY_S:
            return False
        self._last_probe = now
        env = self._env()
        if env is None:
            self.detail = "no gamescope socket"
            return False
        if not self._read_dpms():
            self.detail = "no internal connector dpms node"
            return False
        rc, out = self._run(["gamescopectl", "help"], env)
        self._supported = rc == 0 and CONVAR in out
        self.detail = "ok" if self._supported else f"convar missing (rc={rc})"
        return self._supported

    def diagnostics(self):
        """Blocking. For report bundles: tells a missing convar apart from an old gamescope."""
        self.probe()
        env = self._env()
        version = None
        if env is not None:
            rc, out = self._run(["gamescopectl", "version"], env)
            version = out.strip().splitlines()[0][:120] if rc == 0 and out.strip() else None
        return {
            "supported": self._supported,
            "detail": self.detail,
            "asleep": self.asleep,
            "gamescope_version": version,
            "connectors": self._read_dpms(),
        }

    def set(self, asleep: bool) -> bool:
        """Switch the panel and return True only once every internal connector that was lit
        before sleeping reads back the requested state."""
        env = self._env()
        if env is None or not self._supported:
            self.detail = "unsupported"
            return False
        if asleep and not self.asleep:
            self._lit = [p for p, s in self._read_dpms().items() if s == "On"]
            if not self._lit:
                self.detail = "no lit internal connector"
                return False
        if asleep:
            # A failed or timed-out command may still have reached gamescope: from here on
            # every wake path must send the reset.
            self.asleep = True
        rc, _ = self._run(["gamescopectl", CONVAR, "1" if asleep else "0"], env)
        if rc != 0:
            self.detail = f"gamescopectl rc={rc}"
            return False
        self.asleep = asleep
        if not self._lit:
            # Wake with no recorded baseline (e.g. clearing a leftover from a previous
            # plugin process): the convar is reset, but nothing proves the panel was lit.
            self.detail = "woken without baseline"
            return False
        want = "Off" if asleep else "On"
        deadline = self._clock() + _READBACK_TIMEOUT_S
        while True:
            states = self._read_dpms(self._lit)
            if len(states) == len(self._lit) and all(s == want for s in states.values()):
                self.detail = "ok"
                return True
            if self._clock() >= deadline:
                self.detail = f"readback {sorted(states.values())} != {want}"
                return False
            self._sleep(_READBACK_STEP_S)
