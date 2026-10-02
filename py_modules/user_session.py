"""Run commands inside the logged-in desktop/game session from the root plugin backend."""

import os
import pwd
from typing import Callable, NamedTuple

from controllers.detect import clean_env, resolve_bin


class UserSession(NamedTuple):
    uid: int
    runtime: str
    user: str


def session_for_uid(uid: int) -> UserSession | None:
    try:
        return UserSession(uid, f"/run/user/{uid}", pwd.getpwuid(uid).pw_name)
    except KeyError:
        return None


def spawn_args(
    session: UserSession,
    argv: list[str],
    resolve: Callable[[str], str] = resolve_bin,
) -> tuple[list[str], dict, dict]:
    """(command, env, subprocess identity kwargs) to run argv as the session's user."""
    uid, runtime, user = session
    env = clean_env()
    env["XDG_RUNTIME_DIR"] = runtime
    env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime}/bus"
    identity = {}
    if os.geteuid() == 0:
        # Not runuser: it opens a PAM login session per call (logind scope, lastlog2
        # write), and at watcher cadence that churn can take systemd down.
        try:
            account = pwd.getpwuid(uid)
            gid, home, shell = account.pw_gid, account.pw_dir, account.pw_shell
        except KeyError:
            gid, home, shell = uid, None, None
        try:
            groups = os.getgrouplist(user, gid)
        except OSError:
            groups = [gid]
        identity = {"user": uid, "group": gid, "extra_groups": groups}
        env["USER"] = env["LOGNAME"] = user
        if home:
            env["HOME"] = home
        if shell:
            env["SHELL"] = shell
    return [resolve(argv[0]), *argv[1:]], env, identity
