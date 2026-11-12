from dataclasses import dataclass
import os
import shutil
import subprocess

from mangohud.config import build_presets_conf
from mangohud import ownership
from mangohud.detect import session_alive
from mangohud.opened import OpenWatch

_PROC = "/proc"
_DELIVERY_WAIT_S = 0.75


@dataclass(frozen=True)
class ReloadResult:
    requested: tuple[tuple[int, int], ...]
    pending: tuple[tuple[int, int], ...]
    delivery: str = "unknown"


def clear_presets(path, *, owner=None, trusted_root=None, raise_conflict=False):
    """Restore a file that existed before Panel de Control, or remove only our own."""
    try:
        ownership.restore_managed(path, owner=owner, trusted_root=trusted_root)
    except ownership.HudOwnershipConflict:
        if raise_conflict:
            raise
        return False
    except OSError:
        return False
    return True


def apply_hud(
    model,
    path,
    values=None,
    owner=None,
    replace_conflict=False,
    trusted_root=None,
):
    """Write the model to presets.conf atomically and return exact file readback."""
    desired = build_presets_conf(model, values)
    result = ownership.write_managed(
        path,
        desired,
        owner=owner,
        replace_conflict=replace_conflict,
        trusted_root=trusted_root,
    )
    if result.content != desired:
        raise OSError("MangoHud presets readback does not match the requested config")
    return result.content


def reload_sessions(sessions, proc_root=_PROC, watch_factory=None, *, observe=True, via_proc_cwd=False):
    """Ask every session to reload. With `observe`, delivery is confirmed by
    mangoapp re-opening presets.conf; an unconfirmed request is retried once
    through the other working-directory path and then reported, not resent."""
    sessions = tuple(sessions)
    if not sessions:
        return ReloadResult((), ())
    if not observe:
        return _request_reloads(sessions, proc_root, via_proc_cwd)
    watch_factory = watch_factory or OpenWatch
    with watch_factory(sessions[0].presets_path) as watch:
        result = _request_reloads(sessions, proc_root, via_proc_cwd)
        if not result.requested or not watch.available:
            return result
        opened = watch.opened(_DELIVERY_WAIT_S)
    if opened is None:
        return result
    if opened:
        return ReloadResult(
            result.requested,
            result.pending,
            "observed_proc_cwd" if via_proc_cwd else "observed",
        )
    # The IPC queue is keyed on the working directory; a path read from outside
    # mangoapp's mount namespace can name a different directory than its own.
    with watch_factory(sessions[0].presets_path) as watch:
        retry = _request_reloads(sessions, proc_root, not via_proc_cwd)
        opened = watch.opened(_DELIVERY_WAIT_S) if retry.requested else False
    if opened:
        return ReloadResult(
            retry.requested,
            retry.pending,
            "observed" if via_proc_cwd else "observed_proc_cwd",
        )
    return ReloadResult((), result.pending, "unobserved")


def _request_reloads(sessions, proc_root, via_proc_cwd=False):
    identities = tuple((session.pid, session.starttime) for session in sessions)
    search_path = os.pathsep.join(
        part for part in (os.environ.get("PATH"), "/usr/local/bin:/usr/bin:/bin") if part
    )
    binary = shutil.which("mangohudctl", path=search_path)
    if binary is None:
        return ReloadResult((), identities)
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    env.pop("LD_PRELOAD", None)
    requested = []
    pending = []
    for session in sessions:
        identity = (session.pid, session.starttime)
        if not session_alive(session, proc_root=proc_root):
            pending.append(identity)
            continue
        try:
            result = subprocess.run(
                [binary, "set", "reload_config", "true"],
                check=False,
                cwd=(
                    os.path.join(proc_root, str(session.pid), "cwd")
                    if via_proc_cwd
                    else session.cwd
                ),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            pending.append(identity)
            continue
        (requested if result.returncode == 0 else pending).append(identity)
    return ReloadResult(tuple(requested), tuple(pending))
