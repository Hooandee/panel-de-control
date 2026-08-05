from dataclasses import dataclass
import os
import shutil
import subprocess

from mangohud.config import build_presets_conf
from mangohud import ownership
from mangohud.detect import session_alive

_PROC = "/proc"


@dataclass(frozen=True)
class ReloadResult:
    requested: tuple[tuple[int, int], ...]
    pending: tuple[tuple[int, int], ...]


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


def reload_sessions(sessions, proc_root=_PROC):
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
                cwd=session.cwd,
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
