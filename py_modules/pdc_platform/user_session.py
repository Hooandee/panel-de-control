from __future__ import annotations

import glob
import os
import pwd

from user_session import UserSession, spawn_args

from .host_env import resolve_bin


def find_session():
    """Return the session owning the active PipeWire socket."""
    for sock in glob.glob("/run/user/*/pipewire-0"):
        runtime = os.path.dirname(sock)
        try:
            uid = int(os.path.basename(runtime))
            return uid, runtime, pwd.getpwuid(uid).pw_name
        except (ValueError, KeyError):
            continue
    return None


def session_command(session, argv):
    """Build argv, env and identity to run a PipeWire client inside the user's session."""
    if not session:
        return None, None, None
    cmd, env, identity = spawn_args(UserSession(*session), argv, resolve=lambda name: resolve_bin(name))
    env["LC_ALL"] = "C"  # pactl field labels ("Name:", "Active Port:") must stay English to parse
    return cmd, env, identity
