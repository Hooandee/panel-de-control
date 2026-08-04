import glob
import os
import pwd
import re
import subprocess
import time

from controllers.detect import clean_env, resolve_bin


_FEEDBACK_ATOM = "GAMESCOPE_HDR_OUTPUT_FEEDBACK"
_PID_ATOM = "GAMESCOPE_PID"
_LOOK_PQ_ATOM = "GAMESCOPE_COLOR_LOOK_PQ"
_MIXED_LOOK = "<mixed-gamescope-look>"
_UNAVAILABLE_LOOK = "<gamescope-look-readback-unavailable>"


def _session_contexts():
    contexts = []
    for socket_path in glob.glob("/run/user/*/gamescope-*"):
        if re.fullmatch(r"gamescope-\d+", os.path.basename(socket_path)) is None:
            continue
        runtime_dir = os.path.dirname(socket_path)
        try:
            uid = int(os.path.basename(runtime_dir))
            username = pwd.getpwuid(uid).pw_name
        except (KeyError, ValueError):
            continue
        context = (uid, username, runtime_dir)
        if context not in contexts:
            contexts.append(context)
    return contexts


def _display_names():
    displays = []
    for socket_path in sorted(glob.glob("/tmp/.X11-unix/X*")):
        suffix = os.path.basename(socket_path)[1:]
        if suffix.isdigit():
            displays.append(f":{suffix}")
    return displays or [":0"]


def _context_users(session_context):
    if session_context is None:
        return _session_contexts()
    try:
        runtime_dir = session_context[0]
        uid = int(os.path.basename(runtime_dir))
        return [(uid, pwd.getpwuid(uid).pw_name, runtime_dir)]
    except (IndexError, KeyError, TypeError, ValueError):
        return []


def _session_pid(session):
    try:
        pid = session[2][2]
        return pid if isinstance(pid, int) and pid > 0 else None
    except (IndexError, TypeError):
        return None


def _run_root_xprop(uid, username, runtime_dir, display, arguments):
    command = [resolve_bin("xprop"), *arguments]
    if os.geteuid() != uid:
        command = [
            resolve_bin("runuser"), "-u", username, "--",
            resolve_bin("env"),
            f"DISPLAY={display}",
            f"XDG_RUNTIME_DIR={runtime_dir}",
            *command,
        ]
    env = clean_env()
    env.update({"DISPLAY": display, "XDG_RUNTIME_DIR": runtime_dir})
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=1,
            env=env,
        )
    except Exception:  # noqa: BLE001
        return None


def _read_root_properties(uid, username, runtime_dir, display):
    result = _run_root_xprop(
        uid, username, runtime_dir, display,
        ["-root", _PID_ATOM, _FEEDBACK_ATOM],
    )
    return result.stdout if result is not None and result.returncode == 0 else None


def _read_root_string(uid, username, runtime_dir, display, atom):
    result = _run_root_xprop(
        uid, username, runtime_dir, display,
        ["-root", _PID_ATOM, atom],
    )
    return result.stdout if result is not None and result.returncode == 0 else None


def _write_root_string(uid, username, runtime_dir, display, atom, value):
    result = _run_root_xprop(
        uid, username, runtime_dir, display,
        ["-root", "-f", atom, "8u", "-set", atom, value],
    )
    return result is not None and result.returncode == 0


def _parse_root_string(output, atom):
    if not output:
        return None
    pid_match = re.search(rf"{_PID_ATOM}\(CARDINAL\)\s*=\s*(\d+)", output)
    if pid_match is None:
        return None
    value = None
    for line in output.splitlines():
        if not line.startswith(f"{atom}(") or "= " not in line:
            continue
        value = line.split("= ", 1)[1].strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        break
    return int(pid_match.group(1)), value


class GamescopeLookAtom:
    def __init__(self, atom=_LOOK_PQ_ATOM, read_root=_read_root_string,
                 write_root=_write_root_string, displays=_display_names):
        self._atom = atom
        self._read_root = read_root
        self._write_root = write_root
        self._displays = displays
        self._selected = None

    def _observations(self, session):
        observations = []
        expected_pid = _session_pid(session)
        if expected_pid is None:
            return observations
        for uid, username, runtime_dir in _context_users(session):
            for display in self._displays():
                parsed = _parse_root_string(
                    self._read_root(
                        uid, username, runtime_dir, display, self._atom
                    ),
                    self._atom,
                )
                if parsed is not None:
                    pid, value = parsed
                    if pid != expected_pid:
                        continue
                    observations.append((
                        uid, username, runtime_dir, display, pid, value,
                    ))
        return observations

    def _target(self, session):
        identity = _session_fields(session).get("session_identity")
        observations = self._observations(session)
        pids = {item[4] for item in observations}
        if not observations or len(pids) != 1:
            self._selected = None
            return None
        if self._selected is not None and self._selected[0] == identity:
            selected_display = self._selected[1]
            for item in observations:
                if item[3] == selected_display:
                    return item
        target = observations[0]
        self._selected = (identity, target[3])
        return target

    def read(self, session):
        observations = self._observations(session)
        if not observations or len({item[4] for item in observations}) != 1:
            return _UNAVAILABLE_LOOK
        values = {item[5] for item in observations if item[5]}
        if len(values) > 1:
            return _MIXED_LOOK
        return next(iter(values), None)

    def write(self, session, value):
        target = self._target(session)
        if target is None:
            return False
        uid, username, runtime_dir, display, _pid, _old = target
        if not self._write_root(
            uid, username, runtime_dir, display, self._atom, value
        ):
            return False
        observed = self.read(session)
        return observed == (value or None)


def _select_feedback(observations):
    if not observations:
        return None
    pids = {pid for pid, _value in observations}
    values = {value for _pid, value in observations}
    if len(pids) != 1 or len(values) != 1:
        return None
    return observations[0][1]


def _session_fields(session):
    try:
        return {"session_identity": session[2]} if session is not None else {}
    except (IndexError, TypeError):
        return {}


def _read_hdr_feedback(session_context=None, read_root=_read_root_properties,
                       displays=_display_names):
    observations = []
    expected_pid = _session_pid(session_context)
    if session_context is not None and expected_pid is None:
        return None
    for uid, username, runtime_dir in _context_users(session_context):
        for display in displays():
            output = read_root(uid, username, runtime_dir, display) or ""
            pid = re.search(
                rf"{_PID_ATOM}\(CARDINAL\)\s*=\s*(\d+)", output
            )
            feedback = re.search(
                rf"{_FEEDBACK_ATOM}\(CARDINAL\)\s*=\s*([01])", output
            )
            if pid and feedback:
                observed_pid = int(pid.group(1))
                if expected_pid is not None and observed_pid != expected_pid:
                    continue
                observations.append((
                    observed_pid, feedback.group(1) == "1"
                ))
    return _select_feedback(observations)


class HdrBackend:
    def __init__(self, runner, feedback_reader=None, sleep=time.sleep,
                 readback_attempts=10, readback_interval=0.05,
                 session_provider=None):
        self._run = runner
        self._feedback_reader = feedback_reader or _read_hdr_feedback
        self._sleep = sleep
        self._readback_attempts = max(1, int(readback_attempts))
        self._readback_interval = max(0, float(readback_interval))
        self._session_provider = session_provider
        self._last_operation = None

    def set_enabled(self, on):
        session = (
            self._session_provider()
            if self._session_provider is not None else None
        )
        rc, output = self._run(["hdr_enabled", "1" if on else "0"])
        desired = bool(on)
        response = (output or "").strip()[:200]
        if rc != 0:
            self._last_operation = {
                "enabled": desired,
                "ok": False,
                "rc": rc,
                **_session_fields(session),
                **({"response": response} if response else {}),
            }
            return False

        if self._session_provider is not None:
            current_session = self._session_provider()
            if session is None or current_session != session:
                self._last_operation = {
                    "enabled": desired,
                    "ok": False,
                    "rc": rc,
                    "readback": False,
                    "reason": "session_changed",
                    **_session_fields(session),
                }
                return False

        self._run(["debug_force_repaint"])
        actual = None
        has_readback = False
        for attempt in range(self._readback_attempts):
            value = self._feedback_reader(session)
            if isinstance(value, bool):
                actual = value
                has_readback = True
                if value == desired:
                    self._last_operation = {
                        "enabled": desired,
                        "actual_enabled": actual,
                        "ok": True,
                        "rc": rc,
                        "readback": True,
                        **_session_fields(session),
                    }
                    return True
            if attempt < self._readback_attempts - 1:
                self._sleep(self._readback_interval)

        if has_readback:
            self._last_operation = {
                "enabled": desired,
                "actual_enabled": actual,
                "ok": False,
                "rc": rc,
                "readback": True,
                "reason": "feedback_mismatch",
                **_session_fields(session),
            }
            return False
        self._last_operation = {
            "enabled": desired,
            "actual_enabled": None,
            "ok": True,
            "rc": rc,
            "readback": False,
            "confirmation": "accepted",
            **_session_fields(session),
        }
        return True

    def diagnostics(self):
        return (
            dict(self._last_operation)
            if self._last_operation is not None
            else None
        )
