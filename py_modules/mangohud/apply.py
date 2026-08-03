from dataclasses import dataclass
import os
import shutil
import subprocess

from mangohud.config import build_presets_conf
from mangohud import ownership
from mangohud.detect import session_alive

_PROC = "/proc"
read_presets = ownership.read_text
_write_atomic = ownership._write_atomic


@dataclass(frozen=True)
class ReloadResult:
    requested: tuple[tuple[int, int], ...]
    pending: tuple[tuple[int, int], ...]


def clear_presets(path):
    """Restore a file that existed before Panel de Control, or remove only our own."""
    try:
        ownership.restore_managed(path)
    except (OSError, ownership.HudOwnershipConflict):
        return False
    return True


def apply_hud(model, path, values=None, owner=None):
    """Write the model to presets.conf atomically and return exact file readback."""
    desired = build_presets_conf(model, values)
    result = ownership.write_managed(path, desired, owner=owner)
    if result.content is None:
        raise OSError("MangoHud presets readback is missing")
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


def _process_uid(pid):
    try:
        with open(f"{_PROC}/{pid}/status") as handle:
            for line in handle:
                if line.startswith("Uid:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def _mangoapp_cwd(uid=None):
    try:
        entries = sorted(
            (entry for entry in os.scandir(_PROC) if entry.name.isdigit()),
            key=lambda entry: int(entry.name),
        )
    except OSError:
        return None
    for entry in entries:
        try:
            with open(f"{_PROC}/{entry.name}/comm") as handle:
                if handle.read().strip() == "mangoapp":
                    if uid is not None and _process_uid(entry.name) != uid:
                        continue
                    return os.readlink(f"{_PROC}/{entry.name}/cwd")
        except OSError:
            continue
    return None


def reload_mangoapp(uid=None):
    """Ask mangoapp to re-read Steam's config and the selected preset."""
    cwd = _mangoapp_cwd() if uid is None else _mangoapp_cwd(uid)
    if cwd is None:
        return False
    search_path = os.pathsep.join(
        part for part in (os.environ.get("PATH"), "/usr/local/bin:/usr/bin:/bin") if part
    )
    binary = shutil.which("mangohudctl", path=search_path)
    if binary is None:
        return False
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    env.pop("LD_PRELOAD", None)
    try:
        result = subprocess.run(
            [binary, "set", "reload_config", "true"],
            check=False,
            cwd=cwd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0
