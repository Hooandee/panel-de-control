import os
import shutil
import subprocess

from mangohud.config import build_presets_conf


def read_presets(path):
    """The presets.conf text on disk, or None if it isn't there."""
    try:
        with open(path) as handle:
            return handle.read()
    except OSError:
        return None


def _write_atomic(path, text):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        handle.write(text)
    os.replace(tmp, path)


def clear_presets(path):
    """Remove our presets.conf so MangoHud falls back to its stock presets — the
    honest "HUD off" (we stop hijacking Steam's overlay levels). Idempotent."""
    try:
        os.remove(path)
    except OSError:
        pass


def apply_hud(model, path, values=None):
    """Write the model to presets.conf atomically and return what actually landed
    on disk (readback — the UI reflects reality, never an assumed write). `values`
    (pdc id -> value string) bakes the live plugin-state values into the pdc rows."""
    _write_atomic(path, build_presets_conf(model, values))
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
            cwd=_mangoapp_cwd(),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0
