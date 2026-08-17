"""PipeWire filter-chain lifecycle for the system EQ."""
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
_DEFAULT_SET_DELAYS = (0, 0.1, 0.2)
_DEFAULT_CONFIRM_TIMEOUT_S = 8.0
_RETRY_MIN_S = 15.0
_RETRY_MAX_S = 60.0
_RETRY_MAX_ATTEMPTS = 3
_MAX_ENTRY_BYTES = 64 * 1024
_MISSING_PARENT = object()
_RETRY_OPERATIONS = {
    "config": "config_write",
    "default": "default_sink",
    "link": "target_link",
    "marker": "pending_marker_cleanup",
    "service": "service_restart",
    "teardown": "teardown",
}


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
    """Return the bounded subset of links involved in EQ routing."""
    if not pw_link_text:
        return ""
    keep = ("pdc_eq", "alsa_output", "bluez_output", "loopback")
    out, keeping = [], False
    for line in pw_link_text.splitlines():
        if line[:1] not in (" ", "\t"):
            keeping = any(k in line.lower() for k in keep)
        if keeping:
            out.append(line)
    return "\n".join(out)[:cap]


def _find_session():
    """Return the session owning the active PipeWire socket."""
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
        self._default_failure = None
        self._first_enable_pending = False
        self._first_enable_downstream = None
        self._first_enable_volume = None
        self._first_enable_volumes = None
        self._first_enable_mute = None
        self._cleanup_pending = False
        self._last_applied = None
        self._last_apply = None
        self._active = False
        self._owns_sink = False
        self._user_vol = None
        self._downstream_volumes = {}
        self._downstream_mutes = {}
        self._pending_restores = []
        self._test_proc = None
        self._sleep = time.sleep
        self._monotonic = time.monotonic
        self._retry_request = None
        self._retry_at = 0.0
        self._retry_delay = _RETRY_MIN_S
        self._retry_attempts = 0
        self._retry_service_token = None
        self._retry_recovery = None
        self._name = name or "Panel de Control"
        self._label = f"{self._name} EQ"

    def _session_cmd(self, argv):
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

    def _session_ids(self):
        try:
            account = pwd.getpwuid(self._session[0])
            return account.pw_uid, account.pw_gid
        except KeyError:
            return self._session[0], self._session[0]

    def _open_parent_dir(self, path, *, create=False, missing_ok=False):
        if not path or not self._session or not os.path.isabs(path):
            return None
        uid, gid = self._session_ids()
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
                        return _MISSING_PARENT if missing_ok else None
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
        parent_fd = self._open_parent_dir(path, missing_ok=True)
        if parent_fd is _MISSING_PARENT:
            return True
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
        uid, gid = self._session_ids()
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
        return self._persist_route_state(
            self._first_enable_downstream,
            self._first_enable_volume,
            "prepared",
            self._first_enable_mute,
            self._first_enable_volumes,
            self._first_enable_mute,
        )

    def _persist_route_state(
        self,
        downstream,
        volume,
        phase,
        muted,
        physical_volumes,
        physical_muted,
    ):
        path = self._pending_path()
        if (
            not path
            or not self._session
            or not downstream
            or not re.fullmatch(r"\d+%", str(volume or ""))
            or phase not in ("prepared", "active")
            or not isinstance(muted, bool)
            or not isinstance(physical_volumes, (list, tuple))
            or not physical_volumes
            or any(
                not re.fullmatch(r"\d+%", str(value))
                for value in physical_volumes
            )
            or not isinstance(physical_muted, bool)
        ):
            return False
        state = {
            "sink": downstream,
            "volume": volume,
            "phase": phase,
            "muted": muted,
            "physical_volumes": list(physical_volumes),
            "physical_muted": physical_muted,
            "pending_restores": list(self._pending_restores),
        }
        return self._write_entry(path, json.dumps(state))

    def _route_state(self):
        path = self._pending_path()
        stored = self._read_entry(path) if path else None
        if stored is None:
            return None
        try:
            state = json.loads(stored)
        except (ValueError, TypeError):
            return None
        if not isinstance(state, dict):
            return None
        if (
            "phase" not in state
            and isinstance(state.get("sink"), str)
            and state["sink"]
            and re.fullmatch(r"\d+%", str(state.get("volume", "")))
        ):
            current_default = self._runner(["pactl", "get-default-sink"])
            muted = self._sink_muted(current_default) if current_default else None
            physical_volumes = self._sink_volume_pcts(state["sink"])
            physical_muted = self._sink_muted(state["sink"])
            if muted is not None and physical_volumes and physical_muted is not None:
                state.update({
                    "phase": "prepared",
                    "muted": muted,
                    "physical_volumes": list(physical_volumes),
                    "physical_muted": physical_muted,
                })
        if "pending_restores" not in state:
            state["pending_restores"] = []
        pending_restores = state["pending_restores"]
        if (
            not isinstance(state.get("sink"), str)
            or not state["sink"]
            or not re.fullmatch(r"\d+%", str(state.get("volume", "")))
            or state.get("phase") not in ("prepared", "active")
            or not isinstance(state.get("muted"), bool)
            or not isinstance(state.get("physical_volumes"), list)
            or not state["physical_volumes"]
            or any(
                not re.fullmatch(r"\d+%", str(value))
                for value in state["physical_volumes"]
            )
            or not isinstance(state.get("physical_muted"), bool)
            or not isinstance(pending_restores, list)
            or any(
                not isinstance(item, dict)
                or not isinstance(item.get("sink"), str)
                or not item["sink"]
                or not isinstance(item.get("volumes"), list)
                or not item["volumes"]
                or any(
                    not re.fullmatch(r"\d+%", str(value))
                    for value in item["volumes"]
                )
                or not isinstance(item.get("muted"), bool)
                for item in pending_restores
            )
        ):
            return None
        return state

    def _pending_first_enable(self, downstream):
        path = self._pending_path()
        stored = self._read_entry(path) if path else None
        persisted = bool(path and (stored is not None or self._entry_exists(path)))
        volume = None
        pending = self._route_state()
        if pending is not None and pending["sink"] == downstream:
            volume = pending["volume"]
        if volume is None and self._first_enable_downstream == downstream:
            volume = self._first_enable_volume
        return self._first_enable_pending or persisted, volume

    def _clear_first_enable_pending(self):
        path = self._pending_path()
        if path and not self._remove_entry(path):
            return False
        self._first_enable_pending = False
        self._first_enable_downstream = None
        self._first_enable_volume = None
        self._first_enable_volumes = None
        self._first_enable_mute = None
        return True

    def _discard_first_enable_config(self, conf_path):
        removed = not conf_path or self._remove_entry(conf_path)
        if removed:
            self._clear_first_enable_pending()
        return removed

    def is_supported(self):
        if not self._session:
            self._session = _find_session()
        return (
            bool(self._session)
            and filter_chain_module() is not None
            and self._binary_available("pactl")
            and self._binary_available("pw-link")
        )

    @staticmethod
    def _binary_available(name):
        return resolve_bin(name) != name or shutil.which(name) is not None

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

    def _set_sink_volume_confirmed(self, sink, *values):
        self._runner(["pactl", "set-sink-volume", sink, *values])
        readback = self._sink_volume_pcts(sink)
        if not readback:
            return False
        if len(values) == 1:
            return all(value == values[0] for value in readback)
        return readback == tuple(values)

    def _sink_muted(self, sink):
        value = self._runner(["pactl", "get-sink-mute", sink])
        if value.endswith("yes"):
            return True
        if value.endswith("no"):
            return False
        return None

    def _set_sink_mute_confirmed(self, sink, muted):
        value = "1" if muted else "0"
        self._runner(["pactl", "set-sink-mute", sink, value])
        return self._sink_muted(sink) == bool(muted)

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
            if linked is None:
                conf = self._read_entry(self._conf_path())
                match = re.search(r'\btarget\.object\s*=\s*"((?:\\.|[^"\\])*)"', conf or "")
                if match:
                    try:
                        target = json.loads(f'"{match.group(1)}"')
                    except (TypeError, ValueError):
                        target = None
                    if target in candidates:
                        linked = target
            if linked is None:
                state = self._route_state()
                if state is not None and state["sink"] in candidates:
                    linked = state["sink"]
            if (
                linked is None
                and self._requested_downstream is None
                and self._active_downstream not in candidates
                and configured not in candidates
            ):
                if len(candidates) != 1:
                    return None
                linked = candidates[0]
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

    def _set_default_confirmed(self, sink, expected_downstream=None):
        observed = None
        deadline = self._monotonic() + _DEFAULT_CONFIRM_TIMEOUT_S

        def within_deadline():
            return self._monotonic() < deadline

        def stable(delays):
            nonlocal observed
            for delay in delays:
                if not within_deadline():
                    return False
                if delay:
                    self._sleep(delay)
                if not within_deadline():
                    return False
                observed = self._runner(
                    ["pactl", "get-default-sink"],
                    timeout=1,
                )
                if observed != sink:
                    return False
            return True

        self._default_failure = None
        for delay in _DEFAULT_SET_DELAYS:
            if not within_deadline():
                break
            if delay:
                self._sleep(delay)
            if not within_deadline():
                break
            self._runner(
                ["pactl", "set-default-sink", sink],
                timeout=1,
            )
            if stable(_CONFIRM_DELAYS):
                self._default_failure = None
                return True
            if not observed:
                self._default_failure = {
                    "reason": "default_readback_missing",
                    "current": None,
                }
                return False
            if (
                expected_downstream is not None
                and observed not in (sink, expected_downstream)
            ):
                self._default_failure = {
                    "reason": "downstream_changed_during_default",
                    "current": observed,
                }
                return False
        if not within_deadline():
            self._default_failure = {
                "reason": "default_confirmation_timeout",
                "current": observed or None,
            }
            return False
        self._default_failure = {
            "reason": "default_sink_not_confirmed",
            "current": observed or None,
        }
        return False

    def _target_link_confirmed(self, downstream, *, retry=False, timeout=8):
        delays = _CONFIRM_DELAYS if retry else (0,)
        for delay in delays:
            if delay:
                self._sleep(delay)
            links = self._runner(["pw-link", "-l"], timeout=timeout)
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
        target = downstream if current == self._label else current
        state = self._route_state()
        if state is not None:
            self._pending_restores = list(state["pending_restores"])
        if state is not None and current != self._label and state["sink"] != target:
            previous_pending_restores = list(self._pending_restores)
            if not self._restore_previous_route_state(state, target):
                return False
            if (
                self._pending_restores != previous_pending_restores
                and not self._persist_route_state(
                    state["sink"],
                    state["volume"],
                    state["phase"],
                    state["muted"],
                    state["physical_volumes"],
                    state["physical_muted"],
                )
            ):
                return False
            return True
        owned = (
            target in self._downstream_volumes
            or target in self._downstream_mutes
            or (state is not None and state["sink"] == target)
        )
        if current != self._label and not owned:
            return True
        if not target:
            return False
        prepared = state is not None and state.get("phase") == "prepared"
        volume = (
            state["volume"]
            if prepared and state["sink"] == target
            else self._sink_volume_pct(self._label)
        ) or (state["volume"] if state is not None and state["sink"] == target else None)
        muted = (
            state["muted"]
            if prepared and state["sink"] == target
            else self._sink_muted(self._label)
        )
        if muted is None and state is not None and state["sink"] == target:
            muted = state["muted"]
        if (
            not volume
            or muted is None
            or not self._set_sink_volume_confirmed(target, volume)
            or not self._set_sink_mute_confirmed(target, muted)
        ):
            return False
        if current != target and not self._set_default_confirmed(target):
            return False
        if state is not None and self._pending_restores:
            live_sinks = {
                name
                for name, _status in _sink_candidates(
                    self._runner(["pactl", "list", "short", "sinks"]),
                    self._label,
                )
            }
            previous_pending_restores = list(self._pending_restores)
            if not self._restore_pending_routes(live_sinks - {target}):
                return False
            if (
                self._pending_restores != previous_pending_restores
                and not self._persist_route_state(
                    state["sink"],
                    state["volume"],
                    state["phase"],
                    state["muted"],
                    state["physical_volumes"],
                    state["physical_muted"],
                )
            ):
                return False
        self._downstream_volumes.pop(target, None)
        self._downstream_mutes.pop(target, None)
        self._owns_sink = False
        return True

    def _pin_downstream(self, downstream, balance):
        if downstream not in self._downstream_volumes:
            volumes = self._sink_volume_pcts(downstream)
            if not volumes:
                return False
            self._downstream_volumes[downstream] = volumes
        if downstream not in self._downstream_mutes:
            muted = self._sink_muted(downstream)
            if muted is None:
                return False
            self._downstream_mutes[downstream] = muted
        left, right = balance_channels(balance)
        if not self._set_sink_volume_confirmed(downstream, "100%"):
            return False
        if left != right:
            if not self._set_sink_volume_confirmed(
                downstream,
                f"{left}%",
                f"{right}%",
            ):
                return False
        if not self._set_sink_mute_confirmed(downstream, False):
            return False
        return True

    def _restore_downstream(self, downstream):
        values = self._downstream_volumes.get(downstream)
        muted = self._downstream_mutes.get(downstream)
        if values and not self._set_sink_volume_confirmed(downstream, *values):
            return False
        if isinstance(muted, bool) and not self._set_sink_mute_confirmed(
            downstream,
            muted,
        ):
            return False
        self._downstream_volumes.pop(downstream, None)
        self._downstream_mutes.pop(downstream, None)
        return bool(values) or isinstance(muted, bool)

    def _restore_previous_route_state(self, state, downstream):
        if state is None or state["sink"] == downstream:
            return True
        sinks = self._runner(["pactl", "list", "short", "sinks"])
        names = {name for name, _status in _sink_candidates(sinks, self._label)}
        previous = state["sink"]
        if previous not in names:
            if not any(item["sink"] == previous for item in self._pending_restores):
                self._pending_restores.append({
                    "sink": previous,
                    "volumes": list(state["physical_volumes"]),
                    "muted": state["physical_muted"],
                })
            return True
        if not self._set_sink_volume_confirmed(
            previous,
            *state["physical_volumes"],
        ):
            return False
        if not self._set_sink_mute_confirmed(previous, state["physical_muted"]):
            return False
        self._downstream_volumes.pop(previous, None)
        self._downstream_mutes.pop(previous, None)
        return True

    def _restore_pending_routes(self, names):
        remaining = []
        for item in self._pending_restores:
            if item["sink"] not in names:
                remaining.append(item)
                continue
            if not self._set_sink_volume_confirmed(
                item["sink"],
                *item["volumes"],
            ) or not self._set_sink_mute_confirmed(item["sink"], item["muted"]):
                return False
            self._downstream_volumes.pop(item["sink"], None)
            self._downstream_mutes.pop(item["sink"], None)
        self._pending_restores = remaining
        return True

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
            operation = _RETRY_OPERATIONS.get(self._retry_recovery, "apply")
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

    def _defer_failure(
        self,
        request,
        recovery,
        reason,
        downstream,
        *,
        bypass=False,
        **details,
    ):
        self._defer_retry(request, recovery)
        if bypass:
            details["bypass_confirmed"] = self._bypass_eq_default(downstream)
        self._record_apply(False, reason, downstream=downstream, **details)
        return False

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

    def _fail_activation(self, reason, downstream, **details):
        rollback_confirmed = self.teardown() is True
        self._record_apply(
            False,
            reason,
            downstream=downstream,
            rollback_confirmed=rollback_confirmed,
            **details,
        )
        return False

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

    def sync_state(self):
        state = self._route_state()
        if state is None or state["phase"] != "active":
            return False
        downstream = self._downstream_sink()
        if (
            downstream != state["sink"]
            or self._runner(["pactl", "get-default-sink"]) != self._label
            or not self._target_link_confirmed(downstream)
        ):
            return False
        volume = self._sink_volume_pct(self._label)
        muted = self._sink_muted(self._label)
        if not volume or muted is None:
            return False
        self._pending_restores = list(state["pending_restores"])
        previous_pending_restores = list(self._pending_restores)
        live_sinks = {
            name
            for name, _status in _sink_candidates(
                self._runner(["pactl", "list", "short", "sinks"]),
                self._label,
            )
        }
        linked_sink = _linked_downstream(
            self._runner(["pw-link", "-l"]),
            f"effect_output.{_SINK}",
            live_sinks,
        )
        if not self._restore_pending_routes(live_sinks - {linked_sink}):
            return False
        if (
            volume == state["volume"]
            and muted == state["muted"]
            and self._pending_restores == previous_pending_restores
        ):
            return True
        return self._persist_route_state(
            downstream,
            volume,
            "active",
            muted,
            state["physical_volumes"],
            state["physical_muted"],
        )

    def ensure_sink(self, gains, bass=0, loudness=False, balance=0):
        if not self.is_supported():
            self._record_apply(False, "unsupported")
            return False
        downstream = self._downstream_sink()
        if not downstream:
            self._record_apply(False, "downstream_missing")
            return False
        current_default = self._runner(["pactl", "get-default-sink"])
        state = self._route_state()
        if state is not None:
            self._pending_restores = list(state["pending_restores"])
            previous_pending_restores = list(self._pending_restores)
            live_sinks = {
                name
                for name, _status in _sink_candidates(
                    self._runner(["pactl", "list", "short", "sinks"]),
                    self._label,
                )
            }
            linked_sink = _linked_downstream(
                self._runner(["pw-link", "-l"]),
                f"effect_output.{_SINK}",
                live_sinks,
            )
            if not self._restore_pending_routes(live_sinks - {linked_sink}):
                return self._fail_activation(
                    "pending_route_restore_not_confirmed",
                    downstream,
                )
            if self._pending_restores != previous_pending_restores:
                if not self._persist_route_state(
                    state["sink"],
                    state["volume"],
                    state["phase"],
                    state["muted"],
                    state["physical_volumes"],
                    state["physical_muted"],
                ):
                    return self._fail_activation(
                        "route_state_write_failed",
                        downstream,
                    )
                self._clear_retry()
                state = self._route_state()
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
        first = self._orig_default is None
        conf_path = self._conf_path()
        first_ever = not (conf_path and self._entry_exists(conf_path))
        if first and first_ever:
            self._first_enable_pending = True
            self._first_enable_downstream = downstream
            self._first_enable_volumes = self._sink_volume_pcts(downstream)
            self._first_enable_volume = (
                self._first_enable_volumes[0]
                if self._first_enable_volumes
                else None
            )
            self._first_enable_mute = self._sink_muted(downstream)
            if not self._first_enable_volume:
                self._record_apply(
                    False,
                    "downstream_volume_missing",
                    downstream=downstream,
                )
                return False
            if self._first_enable_mute is None:
                self._record_apply(
                    False,
                    "downstream_mute_missing",
                    downstream=downstream,
                )
                return False
            if not self._persist_first_enable_pending():
                return self._defer_failure(
                    request,
                    "config",
                    "pending_marker_write_failed",
                    downstream,
                )
        configured_same = self._configured_request == request and not first_ever
        service_restarted = False
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
                return self._defer_failure(
                    request,
                    "config",
                    "config_write_failed",
                    downstream,
                    bypass=True,
                    **({"error": write_error} if write_error else {}),
                )
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
                restart_state = self._route_state()
                if restart_state is not None:
                    self._pending_restores = list(
                        restart_state["pending_restores"]
                    )
                    if (
                        restart_state["sink"] != downstream
                        and not any(
                            item["sink"] == restart_state["sink"]
                            for item in self._pending_restores
                        )
                    ):
                        self._pending_restores.append({
                            "sink": restart_state["sink"],
                            "volumes": list(
                                restart_state["physical_volumes"]
                            ),
                            "muted": restart_state["physical_muted"],
                        })
                    preserve_state = (
                        restart_state["phase"] == "active"
                        or restart_state["sink"] == downstream
                    )
                    live_eq_volume = (
                        self._sink_volume_pct(self._label)
                        if restart_state["phase"] == "active"
                        else None
                    )
                    live_eq_mute = (
                        self._sink_muted(self._label)
                        if restart_state["phase"] == "active"
                        else None
                    )
                    if live_eq_volume and live_eq_mute is not None:
                        restart_volume = live_eq_volume
                        restart_mute = live_eq_mute
                    elif preserve_state:
                        restart_volume = restart_state["volume"]
                        restart_mute = restart_state["muted"]
                    else:
                        restart_volume = self._sink_volume_pct(current_default)
                        restart_mute = self._sink_muted(current_default)
                    if restart_state["sink"] == downstream:
                        physical_volumes = restart_state["physical_volumes"]
                        physical_muted = restart_state["physical_muted"]
                    else:
                        physical_volumes = self._sink_volume_pcts(downstream)
                        physical_muted = self._sink_muted(downstream)
                    if (
                        not restart_volume
                        or restart_mute is None
                        or not physical_volumes
                        or physical_muted is None
                        or not self._persist_route_state(
                            downstream,
                            restart_volume,
                            "prepared",
                            restart_mute,
                            physical_volumes,
                            physical_muted,
                        )
                    ):
                        return self._fail_activation(
                            "route_state_write_failed",
                            downstream,
                        )
                    state = self._route_state()
                else:
                    restart_volume = (
                        self._sink_volume_pct(self._label)
                        or self._sink_volume_pct(current_default)
                    )
                    restart_mute = self._sink_muted(self._label)
                    if restart_mute is None:
                        restart_mute = self._sink_muted(current_default)
                    physical_volumes = self._sink_volume_pcts(downstream)
                    physical_muted = self._sink_muted(downstream)
                    if (
                        not restart_volume
                        or restart_mute is None
                        or not physical_volumes
                        or physical_muted is None
                        or not self._persist_route_state(
                            downstream,
                            restart_volume,
                            "prepared",
                            restart_mute,
                            physical_volumes,
                            physical_muted,
                        )
                    ):
                        return self._fail_activation(
                            "route_state_write_failed",
                            downstream,
                        )
                    state = self._route_state()
                if not self._restart():
                    return self._defer_failure(
                        request,
                        "service",
                        "service_restart_failed",
                        downstream,
                        bypass=True,
                    )
                service_restarted = True
                self._configured_request = request
            if not self._target_link_confirmed(downstream, retry=True):
                return self._defer_failure(
                    request,
                    "link",
                    "target_link_not_confirmed",
                    downstream,
                    bypass=True,
                )
        state = self._route_state()
        if state is not None and state["pending_restores"]:
            self._pending_restores = list(state["pending_restores"])
            previous_pending_restores = list(self._pending_restores)
            live_sinks = {
                name
                for name, _status in _sink_candidates(
                    self._runner(["pactl", "list", "short", "sinks"]),
                    self._label,
                )
            }
            linked_sink = _linked_downstream(
                self._runner(["pw-link", "-l"]),
                f"effect_output.{_SINK}",
                live_sinks,
            )
            if not self._restore_pending_routes(live_sinks - {linked_sink}):
                return self._fail_activation(
                    "pending_route_restore_not_confirmed",
                    downstream,
                )
            if self._pending_restores != previous_pending_restores:
                if not self._persist_route_state(
                    state["sink"],
                    state["volume"],
                    state["phase"],
                    state["muted"],
                    state["physical_volumes"],
                    state["physical_muted"],
                ):
                    return self._fail_activation(
                        "route_state_write_failed",
                        downstream,
                    )
                state = self._route_state()
        activation_volume = None
        activation_mute = None
        commit_eq_volume = False
        default_handoff = current_default != self._label
        route_handoff = (
            (state is not None and state["sink"] != downstream)
            or (
                self._active_downstream is not None
                and self._active_downstream != downstream
            )
        )
        if first or default_handoff or route_handoff or service_restarted:
            _pending, pending_volume = self._pending_first_enable(downstream)
            state = self._route_state()
            already_default = current_default == self._label
            if first:
                live_sink = self._label if already_default else downstream
                live_volume = self._sink_volume_pct(live_sink)
                live_mute = self._sink_muted(live_sink)
                active_recovery = (
                    already_default
                    and state is not None
                    and state["sink"] == downstream
                    and state["phase"] == "active"
                )
                activation_volume = (
                    live_volume if active_recovery else pending_volume or live_volume
                )
                activation_mute = (
                    live_mute if active_recovery else state["muted"] if state else live_mute
                )
            else:
                same_route_recovery = (
                    service_restarted
                    and state is not None
                    and state["sink"] == downstream
                )
                activation_volume = (
                    state["volume"]
                    if same_route_recovery
                    else self._sink_volume_pct(self._label) or self._user_vol
                )
                activation_mute = (
                    state["muted"]
                    if same_route_recovery
                    else self._sink_muted(self._label)
                )
            if not activation_volume:
                return self._fail_activation(
                    "downstream_volume_missing",
                    downstream,
                )
            if activation_mute is None:
                return self._fail_activation(
                    "downstream_mute_missing",
                    downstream,
                )
            if not self._restore_previous_route_state(state, downstream):
                return self._fail_activation(
                    "previous_route_state_restore_not_confirmed",
                    downstream,
                )
            if state is not None and state["sink"] == downstream:
                physical_volumes = tuple(state["physical_volumes"])
                physical_muted = state["physical_muted"]
            else:
                physical_volumes = self._sink_volume_pcts(downstream)
                physical_muted = self._sink_muted(downstream)
            if not physical_volumes or physical_muted is None:
                return self._fail_activation(
                    "downstream_snapshot_missing",
                    downstream,
                )
            self._downstream_volumes[downstream] = tuple(physical_volumes)
            self._downstream_mutes[downstream] = physical_muted
            if not self._persist_route_state(
                downstream,
                activation_volume,
                "prepared",
                activation_mute,
                physical_volumes,
                physical_muted,
            ):
                return self._fail_activation(
                    "route_state_write_failed",
                    downstream,
                )
            commit_eq_volume = first or default_handoff or service_restarted
            if default_handoff:
                if not self._set_sink_volume_confirmed(self._label, "100%"):
                    return self._fail_activation(
                        "eq_volume_stage_not_confirmed",
                        downstream,
                    )
            if not self._set_sink_mute_confirmed(self._label, activation_mute):
                return self._fail_activation(
                    "eq_mute_not_confirmed",
                    downstream,
                )
        if not self._set_default_confirmed(self._label, downstream):
            default_failure = dict(self._default_failure or {})
            return self._defer_failure(
                request,
                "default",
                default_failure.get("reason", "default_sink_not_confirmed"),
                downstream,
                bypass=True,
                current=default_failure.get("current"),
            )
        current_downstream = self._downstream_sink()
        if (
            current_downstream != downstream
            or not self._target_link_confirmed(downstream)
        ):
            bypass_confirmed = bool(
                current_downstream
                and self._set_default_confirmed(current_downstream)
            )
            return self._fail_activation(
                "downstream_changed_during_default",
                downstream,
                current=current_downstream,
                bypass_confirmed=bypass_confirmed,
            )
        if commit_eq_volume:
            self._user_vol = activation_volume
            if activation_volume != "100%" and not self._set_sink_volume_confirmed(
                self._label,
                activation_volume,
            ):
                return self._fail_activation(
                    "eq_volume_commit_not_confirmed",
                    downstream,
                )
        if first:
            self._orig_default = downstream
        self._owns_sink = True
        previous_downstream = self._active_downstream
        if (
            previous_downstream
            and previous_downstream != downstream
            and (
                previous_downstream in self._downstream_volumes
                or previous_downstream in self._downstream_mutes
            )
        ):
            if not self._restore_downstream(previous_downstream):
                return self._fail_activation(
                    "previous_downstream_restore_not_confirmed",
                    downstream,
                )
        if not self._pin_downstream(downstream, balance):
            return self._fail_activation(
                "downstream_volume_pin_not_confirmed",
                downstream,
            )
        final_downstream = self._downstream_sink()
        if (
            self._runner(["pactl", "get-default-sink"]) != self._label
            or final_downstream != downstream
            or not self._target_link_confirmed(downstream)
        ):
            return self._fail_activation(
                "post_pin_route_not_confirmed",
                downstream,
                current=final_downstream,
            )
        final_volume = self._sink_volume_pct(self._label)
        final_mute = self._sink_muted(self._label)
        physical_volumes = self._downstream_volumes.get(downstream)
        physical_muted = self._downstream_mutes.get(downstream)
        if not final_volume or final_mute is None or not self._persist_route_state(
            downstream,
            final_volume,
            "active",
            final_mute,
            physical_volumes,
            physical_muted,
        ):
            return self._fail_activation(
                "route_state_write_failed",
                downstream,
            )
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
        return self.ensure_sink(gains, bass, loudness, balance)

    def current_route(self):
        try:
            return route_of_sink(self._runner(["pactl", "list", "sinks"]), self._downstream_sink())
        except Exception:
            return "speaker"

    def is_default(self):
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
        self.stop_test()
        path = self._conf_path()
        had_conf = bool(path and self._entry_exists(path))
        current_default = self._runner(["pactl", "get-default-sink"])
        sinks = self._runner(["pactl", "list", "short", "sinks"])
        all_names = {name for name, _state in _sink_candidates(sinks, "")}
        eq_present = self._label in all_names
        names = all_names - {self._label}
        state = self._route_state()
        if state is not None:
            self._pending_restores = list(state["pending_restores"])
            if (
                state["sink"] not in names
                and not any(
                    item["sink"] == state["sink"]
                    for item in self._pending_restores
                )
            ):
                self._pending_restores.append({
                    "sink": state["sink"],
                    "volumes": list(state["physical_volumes"]),
                    "muted": state["physical_muted"],
                })
        previous_pending_restores = (
            list(state["pending_restores"])
            if state is not None
            else list(self._pending_restores)
        )
        if not self._restore_pending_routes(names):
            return self._defer_failure(
                ("teardown_pending_routes",),
                "teardown",
                "teardown_previous_sink_restore_not_confirmed",
                None,
            )
        if state is not None and self._pending_restores != previous_pending_restores:
            if not self._persist_route_state(
                state["sink"],
                state["volume"],
                state["phase"],
                state["muted"],
                state["physical_volumes"],
                state["physical_muted"],
            ):
                return self._defer_failure(
                    ("teardown_pending_routes",),
                    "marker",
                    "teardown_marker_write_failed",
                    state["sink"],
                )
            self._clear_retry()
            state = self._route_state()
        if (
            state is not None
            and current_default == state["sink"]
            and current_default != self._label
        ):
            transfer_volume = (
                self._sink_volume_pct(self._label)
                if state["phase"] == "active" and eq_present
                else None
            ) or state["volume"]
            transfer_mute = (
                self._sink_muted(self._label)
                if state["phase"] == "active" and eq_present
                else None
            )
            if transfer_mute is None:
                transfer_mute = state["muted"]
            if (
                not self._set_sink_volume_confirmed(
                    state["sink"],
                    transfer_volume,
                )
                or not self._set_sink_mute_confirmed(
                    state["sink"],
                    transfer_mute,
                )
            ):
                return self._defer_failure(
                    ("teardown_owned_default", state["sink"]),
                    "teardown",
                    "teardown_owned_default_restore_not_confirmed",
                    state["sink"],
                )
            self._downstream_volumes.pop(state["sink"], None)
            self._downstream_mutes.pop(state["sink"], None)
        if (
            state is not None
            and current_default not in (self._label, state["sink"])
        ):
            previous_pending_restores = list(self._pending_restores)
            if not self._restore_previous_route_state(state, current_default):
                return self._defer_failure(
                    ("teardown_previous_route", state["sink"]),
                    "teardown",
                    "teardown_previous_sink_restore_not_confirmed",
                    state["sink"],
                )
            if self._pending_restores != previous_pending_restores:
                if not self._persist_route_state(
                    state["sink"],
                    state["volume"],
                    state["phase"],
                    state["muted"],
                    state["physical_volumes"],
                    state["physical_muted"],
                ):
                    return self._defer_failure(
                        ("teardown_previous_route", state["sink"]),
                        "marker",
                        "teardown_marker_write_failed",
                        state["sink"],
                    )
                state = self._route_state()
        runtime_pending = (
            had_conf
            or self._orig_default is not None
            or self._cleanup_pending
            or current_default == self._label
            or eq_present
        )
        if state is not None and not runtime_pending:
            retry_request = ("teardown_journal", state["sink"])
            downstream = state["sink"]
            if self._retry_blocked(retry_request, downstream):
                return False
            if downstream not in names:
                return self._defer_failure(
                    retry_request,
                    "teardown",
                    "teardown_downstream_missing",
                    downstream,
                )
            active_target = current_default == downstream
            volumes = (
                (state["volume"],)
                if active_target
                else tuple(state["physical_volumes"])
            )
            muted = state["muted"] if active_target else state["physical_muted"]
            if not self._set_sink_volume_confirmed(downstream, *volumes):
                return self._defer_failure(
                    retry_request,
                    "teardown",
                    "teardown_volume_not_confirmed",
                    downstream,
                )
            if not self._set_sink_mute_confirmed(downstream, muted):
                return self._defer_failure(
                    retry_request,
                    "teardown",
                    "teardown_mute_not_confirmed",
                    downstream,
                )
            if self._pending_restores:
                return self._defer_failure(
                    retry_request,
                    "teardown",
                    "teardown_pending_sink_missing",
                    downstream,
                )
            if not self._clear_first_enable_pending():
                return self._defer_failure(
                    retry_request,
                    "marker",
                    "teardown_marker_cleanup_failed",
                    downstream,
                )
            self._cleanup_pending = False
            self._active = False
            self._owns_sink = False
            self._clear_retry()
            self._record_apply(True, operation="teardown")
            return True
        if not runtime_pending:
            retry_request = ("teardown_marker",)
            if self._retry_blocked(retry_request, None):
                return False
            if not self._clear_first_enable_pending():
                return self._defer_failure(
                    retry_request,
                    "marker",
                    "teardown_marker_cleanup_failed",
                    None,
                )
            self._cleanup_pending = False
            self._active = False
            self._owns_sink = False
            self._clear_retry()
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
        _pending, pending_volume = (
            self._pending_first_enable(downstream)
            if transfer_volume and downstream
            else (False, None)
        )
        eq_volume = self._sink_volume_pct(self._label) if transfer_volume else None
        our_vol = None
        if transfer_volume:
            if state is not None and state.get("phase") != "active":
                our_vol = pending_volume or eq_volume or self._user_vol
            else:
                our_vol = eq_volume or pending_volume or self._user_vol
        our_mute = (
            self._sink_muted(self._label)
            if transfer_volume
            else None
        )
        if (
            our_mute is None
            and state is not None
            and state["sink"] == downstream
            and isinstance(state.get("muted"), bool)
        ):
            our_mute = state["muted"]
        if transfer_volume:
            if not downstream:
                return self._defer_failure(
                    retry_request,
                    "teardown",
                    "teardown_downstream_missing",
                    downstream,
                )
            if not self._set_sink_volume_confirmed(
                downstream,
                our_vol or "100%",
            ):
                return self._defer_failure(
                    retry_request,
                    "teardown",
                    "teardown_volume_not_confirmed",
                    downstream,
                )
            if our_mute is None or not self._set_sink_mute_confirmed(
                downstream,
                our_mute,
            ):
                return self._defer_failure(
                    retry_request,
                    "teardown",
                    "teardown_mute_not_confirmed",
                    downstream,
                )
            if not self._set_default_confirmed(downstream):
                return self._defer_failure(
                    retry_request,
                    "teardown",
                    "teardown_default_not_confirmed",
                    downstream,
                )
            self._downstream_volumes.pop(downstream, None)
            self._downstream_mutes.pop(downstream, None)
        if had_conf:
            self._remove_entry(path)
        restarted = self._restart()
        sink_absent = restarted and self._sink_absent_confirmed(self._label)
        if not restarted or not sink_absent:
            for sink in list(self._downstream_volumes):
                self._restore_downstream(sink)
            return self._defer_failure(
                retry_request,
                "teardown",
                "teardown_restart_failed" if not restarted else "teardown_sink_still_present",
                downstream,
                bypass=True,
            )
        for sink in list(self._downstream_volumes):
            if not self._restore_downstream(sink):
                return self._defer_failure(
                    retry_request,
                    "teardown",
                    "teardown_previous_sink_restore_not_confirmed",
                    downstream,
                )
        self._orig_default = None
        self._active_downstream = None
        self._requested_downstream = None
        self._configured_default_seen = None
        self._configured_request = None
        self._cleanup_pending = False
        self._last_applied = None
        self._user_vol = None
        self._downstream_volumes = {}
        self._downstream_mutes = {}
        self._clear_retry()
        self._active = False
        self._owns_sink = False
        if self._pending_restores:
            return self._defer_failure(
                retry_request,
                "teardown",
                "teardown_pending_sink_missing",
                downstream,
            )
        if not self._clear_first_enable_pending():
            return self._defer_failure(
                ("teardown_marker",),
                "marker",
                "teardown_marker_cleanup_failed",
                downstream,
            )
        self._record_apply(True, operation="teardown")
        return True
