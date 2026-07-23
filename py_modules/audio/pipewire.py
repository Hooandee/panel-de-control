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
import signal
import subprocess

from audio.filter_chain import build_chain_config
from audio.route import route_of_sink

_DIGITAL_HINTS = ("hdmi", "displayport", "iec958", "spdif")

_SINK = "pdc_eq"
_SERVICE = "filter-chain.service"


def _find_lib(*relative):
    """First matching library path across the prefixes distros actually use: SteamOS/Arch/
    CachyOS put libs in /usr/lib, Fedora/Bazzite in /usr/lib64, Debian/Ubuntu under a
    multiarch triplet dir. Globbed so an untested distro's prefix still resolves."""
    sub = os.path.join(*relative)
    for pattern in (f"/usr/lib*/{sub}", f"/usr/lib/*-linux-gnu/{sub}", f"/usr/local/lib*/{sub}"):
        hits = glob.glob(pattern)
        if hits:
            return hits[0]
    return None


def filter_chain_module():
    return _find_lib("pipewire-0.3", "libpipewire-module-filter-chain.so")


def caps_plugin():
    """The CAPS LADSPA plugin (bass + loudness). Optional — the biquad EQ works without it."""
    return _find_lib("ladspa", "caps.so")


def _os_release():
    out = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                key, sep, val = line.strip().partition("=")
                if sep and key in ("ID", "VARIANT_ID", "VERSION_ID"):
                    out[key] = val.strip('"')
    except OSError:
        pass
    return out


def pick_downstream(short_sinks_text, our_name):
    candidates = []
    for line in (short_sinks_text or "").splitlines():
        parts = line.split("\t")
        name = parts[1] if len(parts) > 1 else ""
        if name and name != our_name:
            candidates.append(name)
    analog = [c for c in candidates if not any(h in c.lower() for h in _DIGITAL_HINTS)]
    picked = analog or candidates
    return picked[0] if picked else None


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
        self._last_applied = None
        self._test_proc = None
        # Human-facing sink name shown in the system/Steam volume OSD (reads node.name),
        # e.g. "Legion Go EQ". Used both as the label and as the sink's node.name.
        self._name = name or "Panel de Control"
        self._label = f"{self._name} EQ"

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
        env["LC_ALL"] = "C"  # pactl field labels ("Name:", "Active Port:") must stay English to parse
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

    def start_test(self, path):
        self.stop_test()
        loop = (
            'SDL_AUDIODRIVER=pulseaudio ffplay -nodisp -loop 0 -volume 100 "$PDC_TEST_WAV" '
            '|| while true; do pw-play "$PDC_TEST_WAV" || sleep 1; done'
        )
        cmd, env = self._session_cmd(["sh", "-c", loop])
        if cmd is None:
            return
        env["PDC_TEST_WAV"] = path
        try:
            self._test_proc = subprocess.Popen(  # noqa: S603
                cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, subprocess.SubprocessError):
            self._test_proc = None

    def stop_test(self):
        proc = self._test_proc
        self._test_proc = None
        if proc is None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                proc.terminate()
            except OSError:
                pass

    def is_test_playing(self):
        return self._test_proc is not None and self._test_proc.poll() is None

    def _conf_path(self):
        if not self._session:
            return None
        home = pwd.getpwuid(self._session[0]).pw_dir
        return os.path.join(home, ".config/pipewire/filter-chain.conf.d/pdc-eq.conf")

    # --- capability ---------------------------------------------------------------
    def is_supported(self):
        return bool(self._session) and filter_chain_module() is not None

    # --- lifecycle ----------------------------------------------------------------
    def _write_conf(self, gains, bass, loudness):
        path = self._conf_path()
        if not path:
            return False
        uid = self._session[0]
        # Create the config dirs owned by the session user (root would otherwise leave
        # ~/.config/pipewire root-owned, so the user couldn't manage their own filters).
        d = os.path.dirname(path)
        made = []
        while d and not os.path.exists(d):
            made.append(d)
            d = os.path.dirname(d)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        for created in made:
            try:
                os.chown(created, uid, uid)
            except OSError:
                pass
        with open(path, "w") as f:
            f.write(build_chain_config(gains, _SINK, self._label, bass, loudness, caps_plugin()))
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
        return pick_downstream(self._runner(["pactl", "list", "short", "sinks"]), self._label)

    def ensure_sink(self, gains, bass=0, loudness=False):
        """Create/refresh the EQ sink (bands + optional bass enhancer), make it default,
        and keep the physical sink it feeds pinned at unity (100%). Steam's volume controls
        the default sink — i.e. ours — so the downstream must stay transparent, or its level
        becomes a hidden second attenuation the user can't reach. Re-pinning unity every
        apply is self-healing across resume/reload (no volume snapshot to drift or corrupt).

        Diff-gated: an unchanged (gains, bass) skips the conf rewrite + ~1s restart (just
        re-asserts default + unity), so a game change with the same sound does no work."""
        if not self.is_supported():
            return False
        applied = (list(gains), bass, loudness)
        unchanged = self._orig_default is not None and applied == self._last_applied
        if not unchanged and not self._write_conf(gains, bass, loudness):
            return False
        downstream = self._downstream_sink()
        first = self._orig_default is None
        if not unchanged:
            self._restart()
        self._runner(["pactl", "set-default-sink", self._label])
        if downstream:
            if first:
                # Enabling shouldn't change loudness: carry the downstream's current level
                # onto our sink (now the volume the user controls) before pinning it unity.
                self._orig_default = downstream
                vol = self._sink_volume_pct(downstream)
                if vol:
                    self._runner(["pactl", "set-sink-volume", self._label, vol])
            self._runner(["pactl", "set-sink-volume", downstream, "100%"])
        self._last_applied = applied
        return True

    def set_gains(self, gains, bass=0, loudness=False):
        """Apply on release: rewrite the conf + restart."""
        return self.ensure_sink(gains, bass, loudness)

    def current_route(self):
        try:
            return route_of_sink(self._runner(["pactl", "list", "sinks"]), self._downstream_sink())
        except Exception:
            return "speaker"

    def is_default(self):
        """True when our EQ sink is the current default output. WirePlumber can re-pick
        the physical device as default on resume/hotplug (dropping the EQ); the watcher
        uses this to re-assert."""
        return self._runner(["pactl", "get-default-sink"]) == self._label

    def diagnostics(self):
        """Read-only audio snapshot for bug reports: why the EQ is (or isn't) available and
        what the graph looks like, so 'no sound' / 'not detected' / volume reports are
        diagnosable. Never raises."""
        info = {
            "supported": self.is_supported(),
            "module": filter_chain_module(),
            "caps": caps_plugin(),
            "os_release": _os_release(),
            "session": None,
        }
        if self._session:
            info["session"] = {"uid": self._session[0], "user": self._session[2]}
        try:
            downstream = self._downstream_sink()
            info.update({
                "default_sink": self._runner(["pactl", "get-default-sink"]) or None,
                "default_is_eq": self.is_default(),
                "sinks": self._runner(["pactl", "list", "short", "sinks"]) or "",
                "downstream": downstream,
                "route": self.current_route(),
                "eq_volume": self._sink_volume_pct(self._label),
                "downstream_volume": self._sink_volume_pct(downstream) if downstream else None,
            })
        except (OSError, subprocess.SubprocessError):
            pass
        path = self._conf_path()
        info["conf_path"] = path
        try:
            info["conf"] = open(path).read() if path and os.path.exists(path) else None
        except OSError:
            info["conf"] = None
        return info

    def teardown(self):
        """Remove the sink and hand the user's current level back to the physical sink
        (fail-safe on disable/unload). No-op when we never created a sink — otherwise we'd
        needlessly restart the shared filter-chain service (interrupting the user's own
        filters) on every unload."""
        self.stop_test()
        path = self._conf_path()
        had_conf = bool(path and os.path.exists(path))
        if not had_conf and self._orig_default is None:
            return
        downstream = self._orig_default or self._downstream_sink()
        our_vol = self._sink_volume_pct(self._label)  # the level the user set while EQ was on
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
        self._last_applied = None
