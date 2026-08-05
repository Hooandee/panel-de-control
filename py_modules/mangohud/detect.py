from dataclasses import dataclass
import os

_PRESETS_FLAG = "STEAM_MANGOAPP_PRESETS_SUPPORTED"
_PROC = "/proc"


@dataclass(frozen=True)
class HudSession:
    pid: int
    starttime: int
    uid: int
    cwd: str
    presets_path: str
    presets_supported: bool


def presets_supported(environ):
    """Whether mangoapp advertises native presets.conf support (Steam sets this on
    builds that resolve preset=N via presets.conf)."""
    return environ.get(_PRESETS_FLAG) == "1"


def _inside_home(path, home):
    try:
        trusted_home = os.path.realpath(home)
        return os.path.commonpath((os.path.realpath(path), trusted_home)) == trusted_home
    except (TypeError, ValueError):
        return False


def presets_path(environ, home):
    """Where MangoHud reads presets.conf: an explicit MANGOHUD_PRESETSFILE, else
    $XDG_CONFIG_HOME/MangoHud/presets.conf, else <HOME>/.config/MangoHud/presets.conf.
    `home` is the trusted Decky-user home. Process-provided paths are honoured only
    inside it so an unprivileged process cannot steer the root backend elsewhere."""
    default = os.path.join(home, ".config", "MangoHud", "presets.conf")
    explicit = environ.get("MANGOHUD_PRESETSFILE")
    if explicit and _inside_home(explicit, home):
        return explicit
    xdg = environ.get("XDG_CONFIG_HOME")
    base = xdg if xdg and _inside_home(xdg, home) else os.path.join(home, ".config")
    candidate = os.path.join(base, "MangoHud", "presets.conf")
    if not _inside_home(candidate, home):
        return default
    return candidate


def _process_starttime(pid, proc_root):
    try:
        with open(os.path.join(proc_root, str(pid), "stat")) as handle:
            raw = handle.read().strip()
        closing = raw.rfind(")")
        if closing < 0:
            return None
        fields = raw[closing + 1:].split()
        return int(fields[19])
    except (OSError, ValueError, IndexError):
        return None


def _process_environ(pid, proc_root):
    try:
        with open(os.path.join(proc_root, str(pid), "environ"), "rb") as handle:
            raw = handle.read()
    except OSError:
        return None
    environ = {}
    for entry in raw.split(b"\0"):
        if b"=" not in entry:
            continue
        key, _, value = entry.partition(b"=")
        environ[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    return environ


def detect_sessions(home=None, uid=None, proc_root=_PROC):
    home = home or os.path.expanduser("~")
    try:
        pids = sorted((int(entry) for entry in os.listdir(proc_root) if entry.isdigit()))
    except OSError:
        return ()
    sessions = []
    for pid in pids:
        process = os.path.join(proc_root, str(pid))
        try:
            with open(os.path.join(process, "comm")) as handle:
                if handle.read().strip() != "mangoapp":
                    continue
            process_uid = _process_uid_at(pid, proc_root)
            if process_uid is None or (uid is not None and process_uid != uid):
                continue
            starttime = _process_starttime(pid, proc_root)
            environ = _process_environ(pid, proc_root)
            cwd = os.readlink(os.path.join(process, "cwd"))
        except OSError:
            continue
        if starttime is None or environ is None:
            continue
        sessions.append(HudSession(
            pid=pid,
            starttime=starttime,
            uid=process_uid,
            cwd=cwd,
            presets_path=presets_path(environ, home),
            presets_supported=presets_supported(environ),
        ))
    return tuple(sessions)


def _process_uid_at(pid, proc_root):
    try:
        with open(os.path.join(proc_root, str(pid), "status")) as handle:
            for line in handle:
                if line.startswith("Uid:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def session_alive(session, proc_root=_PROC):
    process = os.path.join(proc_root, str(session.pid))
    try:
        with open(os.path.join(process, "comm")) as handle:
            if handle.read().strip() != "mangoapp":
                return False
        cwd = os.readlink(os.path.join(process, "cwd"))
    except OSError:
        return False
    return (
        _process_uid_at(session.pid, proc_root) == session.uid
        and _process_starttime(session.pid, proc_root) == session.starttime
        and cwd == session.cwd
    )
