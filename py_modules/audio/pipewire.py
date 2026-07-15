"""Device layer for the EQ sink: writes the filter-chain conf into the user's
filter-chain.conf.d/, restarts the filter-chain service to apply, and sets the sink as
default. Runs session commands (pactl / systemctl --user) against the logged-in user from
the root backend, mirroring the gamescope/fan spawn hygiene (clean_env + XDG_RUNTIME_DIR).
Apply on release: every gain change rewrites the conf and restarts (~1s); live per-band
control isn't available via the CLI on current PipeWire."""
import glob
import os
import pwd
import re
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
        self._orig_volume = None
        self._last_gains = None
        # Human-facing sink name shown in the system/Steam volume UI (the device name).
        self._name = name or "Panel de Control"

    # --- session command plumbing -------------------------------------------------
    def _session_cmd(self, argv):
        """Build (cmd, env) to run `argv` as the logged-in user with a clean env + XDG
        runtime, from the (root) backend. Returns (None, None) with no session."""
        if not self._session:
            return None, None
        from controllers.detect import clean_env

        _uid, runtime, user = self._session
        env = clean_env()
        env["XDG_RUNTIME_DIR"] = runtime
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime}/bus"
        cmd = ["runuser", "-u", user, "--", *argv] if os.geteuid() == 0 else list(argv)
        return cmd, env

    def _run(self, argv, timeout=8):
        """Run a session command and return its stdout (or ''). Never raises."""
        cmd, env = self._session_cmd(argv)
        if cmd is None:
            return ""
        try:
            out = subprocess.run(
                cmd, env=env, check=False, capture_output=True, timeout=timeout, text=True
            )
            return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    def play_test(self, path):
        """Fire-and-forget: play a reference tone through the default (EQ) sink so the
        user can audition the curve. Non-blocking — doesn't hold the apply executor."""
        cmd, env = self._session_cmd(["pw-play", path])
        if cmd is None:
            return
        try:
            subprocess.Popen(  # noqa: S603 — fixed argv, session env
                cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except (OSError, subprocess.SubprocessError):
            pass

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

    def _sink_volume_pct(self, sink):
        """The sink's front volume as a 'NN%' string, or None."""
        m = re.search(r"(\d+)%", self._runner(["pactl", "get-sink-volume", sink]) or "")
        return f"{m.group(1)}%" if m else None

    def _make_transparent(self, downstream):
        """One volume stage, not two. Our sink is the new default (what the volume keys
        move), but it feeds the previous default which may sit below 100% — so the output
        is capped there and reads as 'stuck quiet'. Move that volume onto our sink and set
        the downstream to unity: same loudness now, full range afterwards. Snapshot the
        downstream volume to restore on teardown."""
        vol = self._sink_volume_pct(downstream)
        if vol:
            self._orig_volume = vol
            self._runner(["pactl", "set-sink-volume", _INPUT, vol])
        self._runner(["pactl", "set-sink-volume", downstream, "100%"])

    def ensure_sink(self, gains):
        """Create/refresh the EQ sink with these gains and make it default. On the first
        takeover we make the insert transparent (see _make_transparent); we don't touch
        volumes again after that, so band edits never disturb the user's level.

        Diff-gated: when the gains match what's already applied (e.g. a game change where
        the effective curve is unchanged) we skip the conf rewrite + the ~1s service
        restart and only re-assert the default sink — no work, no audio interruption."""
        if not self.is_supported():
            return False
        unchanged = self._orig_default is not None and gains == self._last_gains
        if not unchanged and not self._write_conf(gains):
            return False
        new_takeover = self._orig_default is None
        if new_takeover:
            cur = self._runner(["pactl", "get-default-sink"])
            if cur and cur != _INPUT:
                self._orig_default = cur
        if not unchanged:
            self._restart()
        self._runner(["pactl", "set-default-sink", _INPUT])
        if new_takeover and self._orig_default:
            self._make_transparent(self._orig_default)
        self._last_gains = list(gains)
        return True

    def set_gains(self, gains):
        """Apply on release: rewrite the conf + restart."""
        return self.ensure_sink(gains)

    def current_route(self):
        # The active port of the physical sink (our virtual sink has none) tells speaker
        # vs headphone — the default sink is our virtual sink, so read the ports instead.
        return route_of_default_sink(lambda: self._runner(["pactl", "list", "sinks"]))

    def teardown(self):
        """Remove the sink and restore the previous default (fail-safe on disable/unload).
        No-op when we never created a sink — otherwise we'd needlessly restart the shared
        filter-chain service (interrupting the user's own filters) on every unload."""
        path = self._conf_path()
        had_conf = bool(path and os.path.exists(path))
        if not had_conf and self._orig_default is None:
            return
        if had_conf:
            try:
                os.remove(path)
            except OSError:
                pass
        self._restart()
        if self._orig_default:
            if self._orig_volume:
                self._runner(["pactl", "set-sink-volume", self._orig_default, self._orig_volume])
            self._runner(["pactl", "set-default-sink", self._orig_default])
            self._orig_default = None
            self._orig_volume = None
        self._last_gains = None
