"""Device layer for the EQ sink: writes the filter-chain conf into the user's
``filter-chain.conf.d/``, restarts the filter-chain service to apply, sets the sink as
default and its volume as the pre-amp. Runs session commands (pactl / systemctl --user)
against the logged-in user from the root backend, mirroring the gamescope/fan spawn
hygiene (clean_env + XDG_RUNTIME_DIR). "Apply on release": every gain change rewrites the
conf and restarts (~1s) — live per-band control is not available via the CLI on current
PipeWire. Pure bits (volume mapping) are unit-tested; the subprocess path is validated
on-device.

Mechanism validated on SteamOS/PipeWire 1.6.4 — see the design doc and the
pipewire-filter-chain-eq memory."""
import glob
import os
import pwd
import subprocess

from audio.filter_chain import build_chain_config
from audio.route import route_of_default_sink

_SINK = "pdc_eq"
_INPUT = f"effect_input.{_SINK}"
_MODULE = "/usr/lib/pipewire-0.3/libpipewire-module-filter-chain.so"
_SERVICE = "filter-chain.service"


def _find_session():
    """The logged-in user's PipeWire session: (uid, runtime_dir, user) from the pipewire
    socket under /run/user/*, or None when no session is present."""
    for sock in glob.glob("/run/user/*/pipewire-0"):
        runtime = os.path.dirname(sock)
        try:
            uid = int(os.path.basename(runtime))
            return uid, runtime, pwd.getpwuid(uid).pw_name
        except (ValueError, KeyError):
            continue
    return None


class PipeWireEq:
    def __init__(self, runner=None, name="Panel de Control"):
        self._runner = runner or self._run
        self._session = _find_session()
        self._orig_default = None
        # Human-facing sink name shown in the system/Steam volume UI (the device name).
        self._name = name or "Panel de Control"

    # --- session command plumbing -------------------------------------------------
    def _run(self, argv, timeout=8):
        """Run a session command as the logged-in user with a clean env + XDG runtime,
        from the (root) backend. Never raises; returns stdout or ''."""
        if not self._session:
            return ""
        from controllers.detect import clean_env

        uid, runtime, user = self._session
        env = clean_env()
        env["XDG_RUNTIME_DIR"] = runtime
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime}/bus"
        cmd = argv
        if os.geteuid() == 0:
            cmd = ["runuser", "-u", user, "--", *argv]
        try:
            out = subprocess.run(
                cmd, env=env, check=False, capture_output=True, timeout=timeout, text=True
            )
            return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    def _conf_path(self):
        if not self._session:
            return None
        home = pwd.getpwuid(self._session[0]).pw_dir
        return os.path.join(home, ".config/pipewire/filter-chain.conf.d/pdc-eq.conf")

    # --- capability ---------------------------------------------------------------
    def is_supported(self):
        return bool(self._session) and os.path.exists(_MODULE)

    # --- lifecycle ----------------------------------------------------------------
    def _write_conf(self, gains):
        path = self._conf_path()
        if not path:
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(build_chain_config(gains, _SINK, self._name))
        uid = self._session[0]
        try:
            os.chown(path, uid, uid)
        except OSError:
            pass
        return True

    def _restart(self):
        self._runner(["systemctl", "--user", "restart", _SERVICE])

    def ensure_sink(self, gains):
        """Create/refresh the EQ sink with these gains and make it default. We never
        touch the sink VOLUME — that is the user's volume (Steam controls it); changing
        it here would look like the audio dropping on its own. Clip headroom is handled
        by keeping preset boosts modest, not by attenuating the output."""
        if not self.is_supported() or not self._write_conf(gains):
            return False
        if self._orig_default is None:
            cur = self._runner(["pactl", "get-default-sink"])
            if cur and cur != _INPUT:
                self._orig_default = cur
        self._restart()
        self._runner(["pactl", "set-default-sink", _INPUT])
        return True

    def set_gains(self, gains):
        """Apply on release: rewrite the conf + restart."""
        return self.ensure_sink(gains)

    def current_route(self):
        # The active port of the physical sink (our virtual sink has none) tells speaker
        # vs headphone — the default sink is our virtual sink, so read the ports instead.
        return route_of_default_sink(lambda: self._runner(["pactl", "list", "sinks"]))

    def teardown(self):
        """Remove the sink and restore the previous default (fail-safe on disable/unload)."""
        path = self._conf_path()
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        self._restart()
        if self._orig_default:
            self._runner(["pactl", "set-default-sink", self._orig_default])
            self._orig_default = None
