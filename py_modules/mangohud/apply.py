import os
import shutil
import subprocess
import tempfile

from mangohud.config import build_presets_conf

_PROC = "/proc"
_BACKUP_SUFFIX = ".pdc-backup"
_MANAGED_SUFFIX = ".pdc-managed"
_MANAGED_STATES = {"1", "managed"}


def read_presets(path):
    """The presets.conf text on disk, or None if it isn't there."""
    try:
        with open(path) as handle:
            return handle.read()
    except OSError:
        return None


def _ensure_directory(path, owner):
    missing = []
    current = path
    while current and not os.path.exists(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    os.makedirs(path, exist_ok=True)
    if owner is not None:
        for created in reversed(missing):
            os.chown(created, *owner)


def _write_atomic(path, text, owner=None):
    directory = os.path.dirname(path)
    if directory:
        _ensure_directory(directory, owner)
    fd, tmp = tempfile.mkstemp(prefix=".presets.", dir=directory or None, text=True)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o644)
            if owner is not None:
                os.fchown(handle.fileno(), *owner)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _owner(path):
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return stat.st_uid, stat.st_gid


def clear_presets(path):
    """Restore a file that existed before Panel de Control, or remove only our own."""
    marker = f"{path}{_MANAGED_SUFFIX}"
    if not os.path.exists(marker):
        return True
    state = read_presets(marker)
    if state is None:
        return False
    state = state.strip()
    backup = f"{path}{_BACKUP_SUFFIX}"
    if os.path.exists(backup):
        try:
            _write_atomic(marker, "restoring\n", _owner(marker))
            os.replace(backup, path)
        except OSError:
            return False
        try:
            os.remove(marker)
        except OSError:
            return False
        return read_presets(path) is not None and not os.path.exists(backup)
    if state == "restoring":
        if read_presets(path) is None:
            return False
        try:
            os.remove(marker)
        except OSError:
            return False
        return True
    if state not in _MANAGED_STATES:
        return False
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        if os.path.lexists(path):
            return False
    try:
        os.remove(marker)
    except OSError:
        return False
    return not os.path.lexists(path)


def apply_hud(model, path, values=None, owner=None):
    """Write the model to presets.conf atomically and return what actually landed
    on disk (readback — the UI reflects reality, never an assumed write). `values`
    (pdc id -> value string) bakes the live plugin-state values into the pdc rows."""
    desired = build_presets_conf(model, values)
    current = read_presets(path)
    marker = f"{path}{_MANAGED_SUFFIX}"
    backup = f"{path}{_BACKUP_SUFFIX}"
    marker_state = read_presets(marker)
    if marker_state is not None:
        marker_state = marker_state.strip()
        if marker_state == "restoring":
            if not clear_presets(path):
                raise OSError("MangoHud presets restore is incomplete")
            current = read_presets(path)
            marker_state = None
        elif marker_state not in _MANAGED_STATES:
            raise OSError("Unknown MangoHud presets ownership marker")
    managed = marker_state in _MANAGED_STATES
    if managed and current == desired:
        return desired
    if not managed:
        if current is None and os.path.exists(backup):
            os.replace(backup, path)
            current = read_presets(path)
        if current is not None:
            _write_atomic(backup, current, owner)
        try:
            _write_atomic(marker, "managed\n", owner)
        except Exception:
            if current is not None:
                try:
                    os.remove(backup)
                except OSError:
                    pass
            raise
    try:
        _write_atomic(path, desired, owner)
    except Exception:
        if not managed:
            clear_presets(path)
        raise
    return read_presets(path)


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
