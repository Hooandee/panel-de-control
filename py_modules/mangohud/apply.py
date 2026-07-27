import os
import shutil
import subprocess
import tempfile

from mangohud.config import build_presets_conf


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


def clear_presets(path):
    """Remove our presets.conf so MangoHud falls back to its stock presets — the
    honest "HUD off" (we stop hijacking Steam's overlay levels). Idempotent."""
    try:
        os.remove(path)
    except FileNotFoundError:
        return True
    except OSError:
        return not os.path.lexists(path)
    return not os.path.lexists(path)


def apply_hud(model, path, values=None, owner=None):
    """Write the model to presets.conf atomically and return what actually landed
    on disk (readback — the UI reflects reality, never an assumed write). `values`
    (pdc id -> value string) bakes the live plugin-state values into the pdc rows."""
    desired = build_presets_conf(model, values)
    if read_presets(path) == desired:
        return desired
    _write_atomic(path, desired, owner)
    return read_presets(path)


def _mangoapp_cwd():
    try:
        entries = os.scandir("/proc")
    except OSError:
        return None
    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                with open(f"/proc/{entry.name}/comm") as handle:
                    if handle.read().strip() == "mangoapp":
                        return os.readlink(f"/proc/{entry.name}/cwd")
            except OSError:
                continue
    return None


def reload_mangoapp():
    """Ask mangoapp to re-read Steam's config and the selected preset."""
    cwd = _mangoapp_cwd()
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
