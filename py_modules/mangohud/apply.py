import os

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
