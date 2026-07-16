import os

_PRESETS_FLAG = "STEAM_MANGOAPP_PRESETS_SUPPORTED"


def presets_supported(environ):
    """Whether mangoapp advertises native presets.conf support (Steam sets this on
    builds that resolve preset=N via presets.conf)."""
    return environ.get(_PRESETS_FLAG) == "1"


def presets_path(environ, home):
    """Where MangoHud reads presets.conf: an explicit MANGOHUD_PRESETSFILE, else
    $XDG_CONFIG_HOME/MangoHud/presets.conf, else <HOME>/.config/MangoHud/presets.conf.
    Prefer the HOME from the mangoapp environ over `home`: we run as root, so our own
    ~ is /root, but the overlay reads the real user's (deck's) config dir."""
    explicit = environ.get("MANGOHUD_PRESETSFILE")
    if explicit:
        return explicit
    base = environ.get("XDG_CONFIG_HOME") or os.path.join(environ.get("HOME") or home, ".config")
    return os.path.join(base, "MangoHud", "presets.conf")


def _mangoapp_environ():
    """The environment of the running mangoapp process, or None if not running.
    Scans /proc, so it isn't unit-tested."""
    proc = "/proc"
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return None
    for pid in pids:
        try:
            with open(os.path.join(proc, pid, "comm")) as handle:
                if handle.read().strip() != "mangoapp":
                    continue
            with open(os.path.join(proc, pid, "environ"), "rb") as handle:
                raw = handle.read()
        except OSError:
            continue
        env = {}
        for entry in raw.split(b"\0"):
            if b"=" in entry:
                key, _, value = entry.partition(b"=")
                env[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
        return env
    return None


def detect():
    """Overlay capability for the HUD tab. `supported` is only True when mangoapp is
    actually running with native presets support. `configFile` is the live
    per-session config Steam feeds mangoapp; None when mangoapp isn't running or
    doesn't expose it."""
    home = os.path.expanduser("~")
    env = _mangoapp_environ()
    if env is None:
        return {"running": False, "supported": False,
                "presetsPath": presets_path({}, home), "configFile": None}
    return {
        "running": True,
        "supported": presets_supported(env),
        "presetsPath": presets_path(env, home),
        "configFile": env.get("MANGOHUD_CONFIGFILE"),
    }
