"""Device layer for the EQ sink: writes the filter-chain conf into the user's
filter-chain.conf.d/, restarts the filter-chain service to apply, and sets the sink as
default. Runs session commands (pactl / systemctl --user) against the logged-in user from
the root backend, mirroring the gamescope/fan spawn hygiene (clean_env + XDG_RUNTIME_DIR).
Apply on release: every gain change rewrites the conf and restarts (~1s); live per-band
control isn't available via the CLI on current PipeWire."""
import glob
import json
import os
import pwd
import re
import secrets
import shutil
import signal
import stat
import subprocess
import time

from audio.const import balance_channels
from audio.filter_chain import build_chain_config
from audio.route import route_of_sink
from controllers.detect import clean_env, resolve_bin
from osinfo import _parse_os_release

_DIGITAL_HINTS = ("hdmi", "displayport", "iec958", "spdif")

_SINK = "pdc_eq"
_SERVICE = "filter-chain.service"
_CONFIRM_DELAYS = (0, 0.05, 0.1, 0.2, 0.4)
_RETRY_MIN_S = 15.0
_RETRY_MAX_S = 60.0
_RETRY_MAX_ATTEMPTS = 3
_MAX_ENTRY_BYTES = 64 * 1024


def _find_lib(*relative):
    # 64-bit-safe order (Fedora/Bazzite: /usr/lib64; SteamOS/Arch/CachyOS: /usr/lib), then the
    # Debian/Ubuntu multiarch dir. Never /usr/lib32 — a 32-bit .so would break the load.
    sub = os.path.join(*relative)
    for base in ("/usr/lib64", "/usr/lib", "/usr/local/lib64", "/usr/local/lib"):
        candidate = os.path.join(base, sub)
        if os.path.exists(candidate):
            return candidate
    for pattern in (f"/usr/lib/*-linux-gnu/{sub}", f"/usr/local/lib/*-linux-gnu/{sub}"):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[0]
    return None


def filter_chain_module():
    return _find_lib("pipewire-0.3", "libpipewire-module-filter-chain.so")


def caps_plugin():
    return _find_lib("ladspa", "caps.so")


def _is_digital(name):
    return any(h in (name or "").lower() for h in _DIGITAL_HINTS)


def _sink_candidates(short_sinks_text, our_name):
    candidates = []
    for line in (short_sinks_text or "").splitlines():
        parts = line.split("\t")
        name = parts[1] if len(parts) > 1 else ""
        state = parts[4] if len(parts) > 4 else ""
        if name and name != our_name:
            candidates.append((name, state))
    return candidates


def pick_downstream(short_sinks_text, our_name):
    candidates = _sink_candidates(short_sinks_text, our_name)
    if not candidates:
        return None
    running = [n for n, s in candidates if s == "RUNNING"]
    if running:
        return running[0]
    pool = [c for c in candidates if not _is_digital(c[0])] or candidates
    return running[0] if running else pool[0][0]


def choose_downstream(
    default_sink,
    short_sinks_text,
    our_name,
    preferred=None,
    linked=None,
    configured=None,
    configured_changed=False,
    requested=None,
):
    candidates = _sink_candidates(short_sinks_text, our_name)
    names = {name for name, _state in candidates}
    if default_sink and default_sink != our_name:
        if not candidates or default_sink in names:
            return default_sink
    if requested and requested in names:
        return requested
    if (
        configured
        and configured in names
        and (configured_changed or preferred is None)
    ):
        return configured
    if linked and linked in names:
        return linked
    if preferred and preferred in names:
        return preferred
    if configured and configured in names:
        return configured
    return pick_downstream(short_sinks_text, our_name)


def _link_reaches(pw_link_text, source, target):
    in_source = False
    for line in (pw_link_text or "").splitlines():
        if line[:1] not in (" ", "\t"):
            in_source = line.strip().rsplit(":", 1)[0] == source
        elif in_source:
            peer = line.strip()
            if peer.startswith("|->") or peer.startswith("|<-"):
                peer = peer[3:].strip().rsplit(":", 1)[0]
                if peer == target:
                    return True
    return False


def _linked_downstream(pw_link_text, source, candidates):
    for candidate in candidates:
        if _link_reaches(pw_link_text, source, candidate):
            return candidate
    return None


def _configured_default_sink(pw_metadata_text):
    for line in (pw_metadata_text or "").splitlines():
        if "key:'default.configured.audio.sink'" not in line:
            continue
        match = re.search(r"value:'(.*?)'\s+type:", line)
        if not match:
            return None
        try:
            value = json.loads(match.group(1))
        except (TypeError, ValueError):
            return None
        name = value.get("name") if isinstance(value, dict) else None
        return name if isinstance(name, str) and name else None
    return None


def _relevant_links(pw_link_text, *, cap=2500):
    """Filter `pw-link -l` to the lines that reveal the EQ routing — our node, hardware
    outputs and loopbacks — keeping each matched node line with its indented `|->`/`|<-`
    continuation. Capped so the report bundle stays small."""
    if not pw_link_text:
        return ""
    keep = ("pdc_eq", "alsa_output", "bluez_output", "loopback")
    out, keeping = [], False
    for line in pw_link_text.splitlines():
        if line[:1] not in (" ", "\t"):  # a node line (not an indented peer)
            keeping = any(k in line.lower() for k in keep)
        if keeping:
            out.append(line)
    return "\n".join(out)[:cap]


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
        self._active_downstream = None
        self._requested_downstream = None
        self._configured_default_seen = None
        self._configured_request = None
        self._first_enable_pending = False
        self._first_enable_downstream = None
        self._first_enable_volume = None
        self._cleanup_pending = False
        self._last_applied = None
        self._last_apply = None
        self._active = False
        self._owns_sink = False
        self._user_vol = None
        self._downstream_volumes = {}
        self._test_proc = None
        self._sleep = time.sleep
        self._monotonic = time.monotonic
        self._retry_request = None
        self._retry_at = 0.0
        self._retry_delay = _RETRY_MIN_S
        self._retry_attempts = 0
        self._retry_service_token = None
        self._retry_recovery = None
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
        _uid, runtime, user = self._session
        env = clean_env()
        env["XDG_RUNTIME_DIR"] = runtime
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime}/bus"
        env["LC_ALL"] = "C"  # pactl field labels ("Name:", "Active Port:") must stay English to parse
        argv = [resolve_bin(argv[0]), *argv[1:]]
        cmd = (
            [resolve_bin("runuser"), "-u", user, "--", *argv]
            if os.geteuid() == 0
            else list(argv)
        )
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
        home = os.path.realpath(pwd.getpwuid(self._session[0]).pw_dir)
        return os.path.join(home, ".config/pipewire/filter-chain.conf.d/pdc-eq.conf")

    def _pending_path(self):
        path = self._conf_path()
        return f"{path}.first-enable-pending" if path else None

    def _open_parent_dir(self, path, *, create=False):
        if not path or not self._session or not os.path.isabs(path):
            return None
        try:
            account = pwd.getpwuid(self._session[0])
            uid, gid = account.pw_uid, account.pw_gid
        except KeyError:
            uid = gid = self._session[0]
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        current_fd = None
        try:
            current_fd = os.open(os.sep, flags)
            parent = os.path.dirname(os.path.normpath(path))
            for component in parent.split(os.sep):
                if not component:
                    continue
                try:
                    next_fd = os.open(component, flags, dir_fd=current_fd)
                except FileNotFoundError:
                    if not create:
                        os.close(current_fd)
                        return None
                    try:
                        os.mkdir(component, 0o755, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                    try:
                        os.chown(
                            component,
                            uid,
                            gid,
                            dir_fd=current_fd,
                            follow_symlinks=False,
                        )
                    except OSError:
                        pass
                    next_fd = os.open(component, flags, dir_fd=current_fd)
                os.close(current_fd)
                current_fd = next_fd
            return current_fd
        except (OSError, ValueError):
            if current_fd is not None:
                try:
                    os.close(current_fd)
                except OSError:
                    pass
            return None

    def _entry_exists(self, path):
        parent_fd = self._open_parent_dir(path)
        if parent_fd is None:
            return False
        try:
            os.stat(os.path.basename(path), dir_fd=parent_fd, follow_symlinks=False)
            return True
        except OSError:
            return False
        finally:
            os.close(parent_fd)

    def _remove_entry(self, path):
        parent_fd = self._open_parent_dir(path)
        if parent_fd is None:
            return False
        name = os.path.basename(path)
        try:
            os.unlink(name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        except OSError:
            return False
        finally:
            os.close(parent_fd)
        return not self._entry_exists(path)

    def _read_entry(self, path):
        parent_fd = self._open_parent_dir(path)
        if parent_fd is None:
            return None
        file_fd = None
        try:
            file_fd = os.open(
                os.path.basename(path),
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=parent_fd,
            )
            entry = os.fstat(file_fd)
            if (
                not stat.S_ISREG(entry.st_mode)
                or entry.st_uid != self._session[0]
            ):
                return None
            chunks = []
            size = 0
            while True:
                chunk = os.read(file_fd, 4096)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_ENTRY_BYTES:
                    return None
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8")
        except (OSError, UnicodeError):
            return None
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(parent_fd)

    def _write_entry(self, path, content):
        data = content.encode("utf-8")
        if len(data) > _MAX_ENTRY_BYTES:
            return False
        parent_fd = self._open_parent_dir(path, create=True)
        if parent_fd is None:
            return False
        name = os.path.basename(path)
        temp_name = f".{name}.{os.getpid()}.{secrets.token_hex(8)}"
        temp_fd = None
        try:
            account = pwd.getpwuid(self._session[0])
            uid, gid = account.pw_uid, account.pw_gid
        except KeyError:
            uid = gid = self._session[0]
        try:
            try:
                existing = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if existing is not None and (
                not stat.S_ISREG(existing.st_mode) or existing.st_uid != uid
            ):
                return False
            temp_fd = os.open(
                temp_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent_fd,
            )
            os.fchmod(temp_fd, 0o600)
            while data:
                written = os.write(temp_fd, data)
                if written <= 0:
                    raise OSError("short write")
                data = data[written:]
            try:
                os.fchown(temp_fd, uid, gid)
            except OSError:
                pass
            if os.fstat(temp_fd).st_uid != uid:
                return False
            os.fsync(temp_fd)
            os.close(temp_fd)
            temp_fd = None
            os.replace(
                temp_name,
                name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            os.fsync(parent_fd)
            return True
        except (OSError, ValueError):
            return False
        finally:
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except OSError:
                    pass
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except OSError:
                pass
            os.close(parent_fd)

    def _persist_first_enable_pending(self):
        path = self._pending_path()
        if not path or not self._session:
            return False
        return self._write_entry(
            path,
            json.dumps(
                {
                    "sink": self._first_enable_downstream,
                    "volume": self._first_enable_volume,
                }
            ),
        )

    def _first_enable_is_pending(self):
        path = self._pending_path()
        return self._first_enable_pending or bool(path and self._entry_exists(path))

    def _pending_first_enable_volume(self, downstream):
        path = self._pending_path()
        if path and self._entry_exists(path):
            try:
                pending = json.loads(self._read_entry(path))
            except (ValueError, TypeError):
                pending = None
            if (
                isinstance(pending, dict)
                and pending.get("sink") == downstream
                and re.fullmatch(r"\d+%", str(pending.get("volume", "")))
            ):
                return pending["volume"]
        if self._first_enable_downstream == downstream:
            return self._first_enable_volume
        return None

    def _clear_first_enable_pending(self):
        path = self._pending_path()
        if path and not self._remove_entry(path):
            return False
        self._first_enable_pending = False
        self._first_enable_downstream = None
        self._first_enable_volume = None
        return True

    def _discard_first_enable_config(self, conf_path):
        removed = not conf_path or self._remove_entry(conf_path)
        if removed:
            self._clear_first_enable_pending()
        return removed

    # --- capability ---------------------------------------------------------------
    def is_supported(self):
        if not self._session:  # re-probe: the session may come up after _init (self-heal)
            self._session = _find_session()
        return (
            bool(self._session)
            and filter_chain_module() is not None
            and self._binary_available("pw-link")
            and self._binary_available("pw-metadata")
        )

    @staticmethod
    def _binary_available(name):
        return resolve_bin(name) != name or shutil.which(name) is not None

    # --- lifecycle ----------------------------------------------------------------
    def _write_conf(self, gains, bass, loudness, downstream=None):
        path = self._conf_path()
        if not path:
            return False
        return self._write_entry(
            path,
            build_chain_config(
                gains,
                _SINK,
                self._label,
                bass,
                loudness,
                caps_plugin(),
                target=downstream,
            ),
        )

    def _service_token(self):
        return self._runner(
            [
                "systemctl",
                "--user",
                "show",
                _SERVICE,
                "--property=InvocationID",
                "--property=MainPID",
                "--value",
            ]
        )

    def _restart(self):
        before = self._service_token()
        self._runner(["systemctl", "--user", "restart", _SERVICE])
        active = self._runner(["systemctl", "--user", "is-active", _SERVICE]) == "active"
        after = self._service_token()
        return active and bool(before) and bool(after) and after != before

    def _sink_volume_pcts(self, sink):
        values = re.findall(
            r"(\d+)%", self._runner(["pactl", "get-sink-volume", sink]) or ""
        )
        return tuple(f"{value}%" for value in values) or None

    def _sink_volume_pct(self, sink):
        values = self._sink_volume_pcts(sink)
        return values[0] if values else None

    def _downstream_sink(self):
        default_sink = self._runner(["pactl", "get-default-sink"])
        sinks = self._runner(["pactl", "list", "short", "sinks"])
        candidates = [name for name, _state in _sink_candidates(sinks, self._label)]
        if self._requested_downstream not in candidates:
            self._requested_downstream = None
        linked = None
        configured = None
        configured_changed = False
        if default_sink == self._label:
            configured = _configured_default_sink(
                self._runner(["pw-metadata", "-n", "default"])
            )
            configured_changed = (
                self._configured_default_seen is not None
                and configured != self._configured_default_seen
            )
            self._configured_default_seen = configured
            if configured in candidates and (
                configured_changed or self._active_downstream is None
            ):
                self._requested_downstream = configured
            linked = _linked_downstream(
                self._runner(["pw-link", "-l"]),
                f"effect_output.{_SINK}",
                candidates,
            )
        elif default_sink in candidates:
            self._requested_downstream = default_sink
        return choose_downstream(
            default_sink,
            sinks,
            self._label,
            preferred=self._active_downstream,
            linked=linked,
            configured=configured,
            configured_changed=configured_changed,
            requested=self._requested_downstream,
        )

    def _set_default_confirmed(self, sink):
        for delay in _CONFIRM_DELAYS:
            if delay:
                self._sleep(delay)
            if sink == self._label:
                value = json.dumps({"name": sink}, separators=(",", ":"))
                self._runner(
                    [
                        "pw-metadata",
                        "-n",
                        "default",
                        "0",
                        "default.audio.sink",
                        value,
                        "Spa:String:JSON",
                    ]
                )
                if self._runner(["pactl", "get-default-sink"]) == sink:
                    return True
                continue
            self._runner(["pactl", "set-default-sink", sink])
            if self._runner(["pactl", "get-default-sink"]) == sink:
                return True
        return False

    def _target_link_confirmed(self, downstream, *, retry=False):
        delays = _CONFIRM_DELAYS if retry else (0,)
        for delay in delays:
            if delay:
                self._sleep(delay)
            links = self._runner(["pw-link", "-l"])
            if _link_reaches(links, f"effect_output.{_SINK}", downstream):
                return True
        return False

    def _sink_absent_confirmed(self, sink):
        for delay in _CONFIRM_DELAYS:
            if delay:
                self._sleep(delay)
            raw = self._runner(["pactl", "list", "short", "sinks"])
            if not raw:
                continue
            names = {
                name
                for name, _state in _sink_candidates(
                    raw,
                    "",
                )
            }
            if names and sink not in names:
                return True
        return False

    def _bypass_eq_default(self, downstream):
        current = self._runner(["pactl", "get-default-sink"])
        if not current:
            return False
        if current != self._label:
            return True
        if not downstream or not self._set_default_confirmed(downstream):
            return False
        volume = self._sink_volume_pct(self._label) or self._user_vol
        self._restore_downstream_volume(downstream)
        if volume:
            self._runner(["pactl", "set-sink-volume", downstream, volume])
        self._owns_sink = False
        return True

    def _pin_downstream(self, downstream, balance):
        """Hold the physical sink at unity, offset per-channel for L/R balance (far side
        attenuated, near side at unity). Pin unity first so a non-stereo sink stays
        transparent when the two-value write fails, rather than a hidden attenuation."""
        if downstream not in self._downstream_volumes:
            self._downstream_volumes[downstream] = self._sink_volume_pcts(downstream)
        left, right = balance_channels(balance)
        self._runner(["pactl", "set-sink-volume", downstream, "100%"])
        if left != right:
            self._runner(["pactl", "set-sink-volume", downstream, f"{left}%", f"{right}%"])

    def _restore_downstream_volume(self, downstream):
        values = self._downstream_volumes.pop(downstream, None)
        if values:
            self._runner(["pactl", "set-sink-volume", downstream, *values])

    def _retry_blocked(self, request, downstream):
        if self._retry_request != request:
            self._clear_retry()
            return False
        if self._retry_attempts >= _RETRY_MAX_ATTEMPTS:
            current_service_token = self._service_token()
            service_changed = (
                bool(self._retry_service_token)
                and bool(current_service_token)
                and current_service_token != self._retry_service_token
            )
            link_recovered = (
                self._retry_recovery == "link"
                and self._configured_request == request
                and self._target_link_confirmed(downstream)
            )
            if service_changed or link_recovered:
                self._clear_retry()
                return False
            operation = {
                "config": "config_write",
                "default": "default_sink",
                "link": "target_link",
                "service": "service_restart",
                "teardown": "teardown",
            }.get(self._retry_recovery, "apply")
            self._record_apply(
                False,
                f"{operation}_retry_exhausted",
                downstream=downstream,
            )
            return True
        remaining = self._retry_at - self._monotonic()
        if remaining <= 0:
            return False
        self._record_apply(
            False,
            "service_restart_backoff",
            downstream=downstream,
            retry_in=round(remaining, 1),
        )
        return True

    def _defer_retry(self, request, recovery):
        self._retry_request = request
        self._retry_attempts += 1
        self._retry_service_token = self._service_token()
        self._retry_recovery = recovery
        self._retry_at = self._monotonic() + self._retry_delay
        self._retry_delay = min(_RETRY_MAX_S, self._retry_delay * 2)

    def _clear_retry(self):
        self._retry_request = None
        self._retry_at = 0.0
        self._retry_delay = _RETRY_MIN_S
        self._retry_attempts = 0
        self._retry_service_token = None
        self._retry_recovery = None

    def _record_apply(self, ok, reason=None, **details):
        if not ok:
            self._active = False
        self._last_apply = {
            "ok": bool(ok),
            **({"reason": reason} if reason is not None else {}),
            **details,
        }

    def apply_diagnostics(self):
        return dict(self._last_apply) if self._last_apply is not None else None

    def is_active(self):
        downstream = self._downstream_sink()
        return (
            self._active
            and self.is_default()
            and downstream is not None
            and downstream == self._active_downstream
            and self._target_link_confirmed(downstream)
        )

    def ensure_sink(self, gains, bass=0, loudness=False, balance=0):
        """Create/refresh the EQ sink (bands + optional bass enhancer), make it default,
        and keep the physical sink it feeds pinned at unity (100%), offset for balance.
        Steam's volume controls the default sink — i.e. ours — so the downstream must stay
        transparent, or its level becomes a hidden second attenuation the user can't reach.
        Re-pinning every apply is self-healing across resume/reload; captured physical levels
        are restored on route handoff and teardown.

        Diff-gated: an unchanged (gains, bass, loudness) skips the conf rewrite + ~1s restart
        (just re-asserts default + the pin). Balance is outside the gate — it only moves the
        pin, so it re-applies without a restart."""
        if not self.is_supported():
            self._record_apply(False, "unsupported")
            return False
        downstream = self._downstream_sink()
        if not downstream:
            self._record_apply(False, "downstream_missing")
            return False
        applied = (list(gains), bass, loudness)
        request = (tuple(gains), bass, bool(loudness), downstream)
        if self._retry_blocked(request, downstream):
            return False
        unchanged = (
            self._orig_default is not None
            and applied == self._last_applied
            and downstream == self._active_downstream
            and self._target_link_confirmed(downstream)
        )
        # First-ever enable (no conf yet) vs a boot re-assert (conf exists) — check before
        # _write_conf creates it.
        first = self._orig_default is None
        conf_path = self._conf_path()
        first_ever = not (conf_path and self._entry_exists(conf_path))
        if first and first_ever:
            self._first_enable_pending = True
            self._first_enable_downstream = downstream
            self._first_enable_volume = self._sink_volume_pct(downstream)
            if not self._persist_first_enable_pending():
                self._defer_retry(request, "config")
                self._record_apply(
                    False,
                    "pending_marker_write_failed",
                    downstream=downstream,
                )
                return False
        configured_same = self._configured_request == request and not first_ever
        if not unchanged and not configured_same:
            try:
                wrote_conf = self._write_conf(gains, bass, loudness, downstream)
            except (OSError, ValueError) as error:
                wrote_conf = False
                write_error = type(error).__name__
            else:
                write_error = None
            if not wrote_conf:
                if first and first_ever:
                    self._discard_first_enable_config(conf_path)
                bypass_confirmed = self._bypass_eq_default(downstream)
                self._defer_retry(request, "config")
                self._record_apply(
                    False,
                    "config_write_failed",
                    downstream=downstream,
                    bypass_confirmed=bypass_confirmed,
                    **({"error": write_error} if write_error else {}),
                )
                return False
        if not unchanged:
            if not configured_same:
                current_default = self._runner(["pactl", "get-default-sink"])
                if current_default not in (self._label, downstream):
                    if first and first_ever:
                        self._discard_first_enable_config(conf_path)
                    self._record_apply(
                        False,
                        "downstream_changed",
                        downstream=downstream,
                        current=current_default or None,
                    )
                    return False
                if not self._restart():
                    self._defer_retry(request, "service")
                    bypass_confirmed = self._bypass_eq_default(downstream)
                    self._record_apply(
                        False,
                        "service_restart_failed",
                        downstream=downstream,
                        bypass_confirmed=bypass_confirmed,
                    )
                    return False
                self._configured_request = request
            if not self._target_link_confirmed(downstream, retry=True):
                self._defer_retry(request, "link")
                bypass_confirmed = self._bypass_eq_default(downstream)
                self._record_apply(
                    False,
                    "target_link_not_confirmed",
                    downstream=downstream,
                    bypass_confirmed=bypass_confirmed,
                )
                return False
        if not self._set_default_confirmed(self._label):
            rollback_confirmed = None
            if first and first_ever:
                self._remove_entry(conf_path)
                self._restart()
                rollback_confirmed = self._sink_absent_confirmed(self._label)
                self._cleanup_pending = not rollback_confirmed
                self._set_default_confirmed(downstream)
                self._configured_request = None
            bypass_confirmed = self._bypass_eq_default(downstream)
            self._defer_retry(request, "default")
            self._record_apply(
                False,
                "default_sink_not_confirmed",
                downstream=downstream,
                bypass_confirmed=bypass_confirmed,
                **(
                    {"rollback_confirmed": rollback_confirmed}
                    if rollback_confirmed is not None
                    else {}
                ),
            )
            return False
        if first:
            if self._first_enable_is_pending():
                # Carry the downstream's level onto our sink so enabling doesn't jump
                # loudness. Skip on a boot re-assert: the sink already holds the user's
                # level (WirePlumber restores it), and the downstream is always unity.
                vol = self._pending_first_enable_volume(
                    downstream
                ) or self._sink_volume_pct(downstream)
                if vol:
                    self._user_vol = vol
                    self._runner(["pactl", "set-sink-volume", self._label, vol])
            if not self._clear_first_enable_pending():
                bypass_confirmed = self._bypass_eq_default(downstream)
                self._defer_retry(request, "config")
                self._record_apply(
                    False,
                    "pending_marker_cleanup_failed",
                    downstream=downstream,
                    bypass_confirmed=bypass_confirmed,
                )
                return False
            self._orig_default = downstream
        self._owns_sink = True
        previous_downstream = self._active_downstream
        if previous_downstream and previous_downstream != downstream:
            self._restore_downstream_volume(previous_downstream)
        self._pin_downstream(downstream, balance)
        self._last_applied = applied
        self._active_downstream = downstream
        if self._requested_downstream == downstream:
            self._requested_downstream = None
        self._active = True
        self._cleanup_pending = False
        self._clear_retry()
        self._record_apply(True, downstream=downstream, unchanged=unchanged)
        return True

    def set_gains(self, gains, bass=0, loudness=False, balance=0):
        """Apply on release: rewrite the conf + restart (balance just moves the pin)."""
        return self.ensure_sink(gains, bass, loudness, balance)

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
        info = {
            "supported": self.is_supported(),
            "module": filter_chain_module(),
            "caps": caps_plugin(),
            "os_release": {k: v for k, v in _parse_os_release().items()
                           if k in ("ID", "VARIANT_ID", "VERSION_ID")},
            "session": None,
        }
        if self._session:
            info["session"] = {"uid": self._session[0]}
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
                # Where the EQ node's output actually routes (does it reach a hardware
                # output, or a virtual/loopback sink that swallows it?). This is the
                # signal that tells a "no sound with the EQ on" report apart: node graph
                # + whether the filter-chain loaded. Filtered to the relevant nodes and
                # capped so the bundle stays small.
                "links": _relevant_links(self._runner(["pw-link", "-l"])),
                "modules": self._runner(["pactl", "list", "short", "modules"]) or "",
            })
        except (OSError, subprocess.SubprocessError):
            pass
        path = self._conf_path()
        info["conf_path"] = path
        info["last_apply"] = self.apply_diagnostics()
        info["conf"] = self._read_entry(path) if path else None
        return info

    def teardown(self):
        """Remove the sink and hand the user's current level back to the physical sink
        (fail-safe on disable/unload). No-op when we never created a sink — otherwise we'd
        needlessly restart the shared filter-chain service (interrupting the user's own
        filters) on every unload."""
        self.stop_test()
        path = self._conf_path()
        had_conf = bool(path and self._entry_exists(path))
        current_default = self._runner(["pactl", "get-default-sink"])
        sinks = self._runner(["pactl", "list", "short", "sinks"])
        all_names = {name for name, _state in _sink_candidates(sinks, "")}
        eq_present = self._label in all_names
        names = all_names - {self._label}
        runtime_pending = (
            had_conf
            or self._orig_default is not None
            or self._cleanup_pending
            or current_default == self._label
            or eq_present
        )
        if not runtime_pending:
            self._clear_first_enable_pending()
            self._active = False
            self._owns_sink = False
            self._record_apply(True, operation="teardown", unchanged=True)
            return True
        self._cleanup_pending = True
        retry_request = ("teardown",)
        if self._retry_blocked(retry_request, self._active_downstream):
            return False
        transfer_volume = current_default == self._label
        downstream = None
        if transfer_volume:
            if self._active_downstream in names:
                downstream = self._active_downstream
            elif self._orig_default in names:
                downstream = self._orig_default
            else:
                downstream = self._downstream_sink()
        our_vol = (
            self._sink_volume_pct(self._label) or self._user_vol
            if transfer_volume
            else None
        )
        if had_conf:
            self._remove_entry(path)
        restarted = self._restart()
        sink_absent = restarted and self._sink_absent_confirmed(self._label)
        if not restarted or not sink_absent:
            bypass_confirmed = self._bypass_eq_default(downstream)
            for sink in list(self._downstream_volumes):
                self._restore_downstream_volume(sink)
            self._defer_retry(retry_request, "teardown")
            self._record_apply(
                False,
                "teardown_restart_failed" if not restarted else "teardown_sink_still_present",
                downstream=downstream,
                bypass_confirmed=bypass_confirmed,
            )
            return False
        for sink in list(self._downstream_volumes):
            self._restore_downstream_volume(sink)
        if transfer_volume and downstream:
            self._runner(
                ["pactl", "set-sink-volume", downstream, our_vol or "100%"]
            )
            if not self._set_default_confirmed(downstream):
                self._defer_retry(retry_request, "teardown")
                self._record_apply(
                    False,
                    "teardown_default_not_confirmed",
                    downstream=downstream,
                )
                return False
        elif transfer_volume:
            self._defer_retry(retry_request, "teardown")
            self._record_apply(False, "teardown_downstream_missing")
            return False
        self._orig_default = None
        self._active_downstream = None
        self._requested_downstream = None
        self._configured_default_seen = None
        self._configured_request = None
        self._clear_first_enable_pending()
        self._cleanup_pending = False
        self._last_applied = None
        self._user_vol = None
        self._downstream_volumes = {}
        self._clear_retry()
        self._active = False
        self._owns_sink = False
        self._record_apply(True, operation="teardown")
        return True
