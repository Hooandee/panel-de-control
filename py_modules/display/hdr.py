"""HDR output on/off via gamescope, with compositor feedback when available."""

import glob
import os
import pwd
import re
import subprocess
import time

from controllers.detect import clean_env, resolve_bin


_FEEDBACK_ATOM = "GAMESCOPE_HDR_OUTPUT_FEEDBACK"
_PID_ATOM = "GAMESCOPE_PID"


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


def _read_root_properties(uid, username, runtime_dir, display):
    xprop = resolve_bin("xprop")
    command = [xprop, "-root", _PID_ATOM, _FEEDBACK_ATOM]
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
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=1,
            env=env,
        )
    except Exception:  # noqa: BLE001
        return None
    return result.stdout if result.returncode == 0 else None


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
                observations.append((
                    int(pid.group(1)), feedback.group(1) == "1"
                ))
    return _select_feedback(observations)


class HdrBackend:
    """Toggles gamescope HDR. `runner(args) -> (rc, stdout)` is the shared gamescopectl
    runner (injected for testing)."""

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
