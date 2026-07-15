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


def pick_downstream(short_sinks_text, our_name):
    """The physical sink our EQ feeds: the first sink in `pactl list short sinks` output
    whose name isn't our virtual sink. None when only ours (or none) is present."""
    for line in (short_sinks_text or "").splitlines():
        parts = line.split("\t")
        name = parts[1] if len(parts) > 1 else ""
        if name and name != our_name:
            return name
    return None


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

    def _downstream_sink(self):
        """The physical sink our EQ feeds (the one that isn't our virtual sink)."""
        return pick_downstream(self._runner(["pactl", "list", "short", "sinks"]), _INPUT)

    def ensure_sink(self, gains):
        """Create/refresh the EQ sink with these gains, make it default, and keep the
        physical sink it feeds pinned at unity (100%). Steam's volume controls the default
        sink — i.e. ours — so the downstream must stay transparent, or its level becomes a
        hidden second attenuation the user can't reach. Re-pinning unity every apply is
        self-healing across resume/reload (no volume snapshot to drift or corrupt).

        Diff-gated: unchanged gains skip the conf rewrite + ~1s restart (just re-assert
        default + unity), so a game change with the same curve does no audible work."""
        if not self.is_supported():
            return False
        unchanged = self._orig_default is not None and gains == self._last_gains
        if not unchanged and not self._write_conf(gains):
            return False
        downstream = self._downstream_sink()
        first = self._orig_default is None
        if not unchanged:
            self._restart()
        self._runner(["pactl", "set-default-sink", _INPUT])
        if downstream:
            if first:
                # Enabling shouldn't change loudness: carry the downstream's current level
                # onto our sink (now the volume the user controls) before pinning it unity.
                self._orig_default = downstream
                vol = self._sink_volume_pct(downstream)
                if vol:
                    self._runner(["pactl", "set-sink-volume", _INPUT, vol])
            self._runner(["pactl", "set-sink-volume", downstream, "100%"])
        self._last_gains = list(gains)
        return True

    def set_gains(self, gains):
        """Apply on release: rewrite the conf + restart."""
        return self.ensure_sink(gains)

    def current_route(self):
        # The active port of the physical sink (our virtual sink has none) tells speaker
        # vs headphone — the default sink is our virtual sink, so read the ports instead.
        return route_of_default_sink(lambda: self._runner(["pactl", "list", "sinks"]))

    def is_default(self):
        """True when our EQ sink is the current default output. WirePlumber can re-pick
        the physical device as default on resume/hotplug (dropping the EQ); the watcher
        uses this to re-assert."""
        return self._runner(["pactl", "get-default-sink"]) == _INPUT

    def teardown(self):
        """Remove the sink and hand the user's current level back to the physical sink
        (fail-safe on disable/unload). No-op when we never created a sink — otherwise we'd
        needlessly restart the shared filter-chain service (interrupting the user's own
        filters) on every unload."""
        path = self._conf_path()
        had_conf = bool(path and os.path.exists(path))
        if not had_conf and self._orig_default is None:
            return
        downstream = self._orig_default or self._downstream_sink()
        our_vol = self._sink_volume_pct(_INPUT)  # the level the user set while EQ was on
        if had_conf:
            try:
                os.remove(path)
            except OSError:
                pass
        self._restart()
        if downstream:
            if our_vol:
                self._runner(["pactl", "set-sink-volume", downstream, our_vol])
            self._runner(["pactl", "set-default-sink", downstream])
        self._orig_default = None
        self._last_gains = None
