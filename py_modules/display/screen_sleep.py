"""Internal panel power through gamescope's `drm_sleep_internal_screen` convar (gamescope
>= 3.16.5). gamescope owns DRM master, so nothing else can switch the connector off; the
connector's `dpms` node is the readback. Blocking: call off the event loop."""

import glob
import os
import re
import subprocess
import threading
import time

CONVAR = "drm_sleep_internal_screen"
_SOCKET = re.compile(r"gamescope-\d+$")
_INTERNAL = re.compile(r"card\d+-(eDP|DSI|LVDS)-")
_PROBE_RETRY_S = 30.0
_READBACK_S = 2.0


def gamescopectl(*args):
    for sock in sorted(glob.glob("/run/user/*/gamescope-*")):
        if not _SOCKET.match(os.path.basename(sock)):
            continue
        env = {"XDG_RUNTIME_DIR": os.path.dirname(sock), "WAYLAND_DISPLAY": os.path.basename(sock)}
        try:
            from controllers.detect import clean_env, resolve_bin
            p = subprocess.run([resolve_bin("gamescopectl"), *args], capture_output=True,
                               text=True, timeout=2, env={**clean_env(), **env})
            # `help` lists convars on stderr.
            return p.returncode, (p.stdout or "") + (p.stderr or "")
        except (OSError, subprocess.SubprocessError):
            return 1, ""
    return 1, ""


class ScreenSleep:
    def __init__(self, ctl=gamescopectl, drm_root="/sys/class/drm", clock=time.monotonic,
                 sleep=time.sleep):
        self._ctl = ctl
        self._drm_root = drm_root
        self._clock = clock
        self._sleep = sleep
        self._probed_at = None
        self.supported = False
        self.asleep = False
        self.detail = "not probed"
        self.version = None
        self._lock = threading.Lock()
        self._closed = False

    def _dpms(self):
        states = []
        for path in sorted(glob.glob(os.path.join(self._drm_root, "card*-*", "dpms"))):
            if _INTERNAL.match(os.path.basename(os.path.dirname(path))):
                try:
                    with open(path) as f:
                        states.append(f.read().strip())
                except OSError:
                    pass
        return states

    def probe(self):
        """Rate-limited; the first success also clears a sleep a crashed process may have left."""
        now = self._clock()
        if self.supported or (self._probed_at is not None and now - self._probed_at < _PROBE_RETRY_S):
            return self.supported
        self._probed_at = now
        rc, out = self._ctl("help")
        self.supported = rc == 0 and CONVAR in out and bool(self._dpms())
        self.detail = "ok" if self.supported else f"unsupported (rc={rc})"
        if self.supported:
            self.version = (self._ctl("version")[1].strip().splitlines() or [None])[0]
            self._ctl(CONVAR, "0")
        return self.supported

    def set(self, asleep):
        """True only once every internal connector reads back the requested state."""
        with self._lock:
            if asleep and self._closed:
                self.detail = "closed"
                return False
            return self._set(asleep)

    def close(self):
        """Final wake: a sleep request already in flight can no longer land after it."""
        with self._lock:
            self._closed = True
            return self._set(False) if self.asleep else True

    def _set(self, asleep):
        if not self.supported:
            return False
        if asleep:
            if not self.asleep and any(s != "On" for s in self._dpms()):
                self.detail = "internal panel not lit"
                return False
            # A failed or timed-out command may still reach gamescope: every wake must reset it.
            self.asleep = True
        rc, _ = self._ctl(CONVAR, "1" if asleep else "0")
        if rc != 0:
            self.detail = f"gamescopectl rc={rc}"
            return False
        self.asleep = asleep
        want = "Off" if asleep else "On"
        deadline = self._clock() + _READBACK_S
        while True:
            states = self._dpms()
            if states and all(s == want for s in states):
                self.detail = "ok"
                return True
            if self._clock() >= deadline:
                self.detail = f"readback {states} != {want}"
                return False
            self._sleep(0.1)
