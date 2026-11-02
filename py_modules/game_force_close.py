"""Force-closes a game Steam could not stop with TerminateApp.

Steam starts every game under its `reaper` (`reaper SteamLaunch AppId=<id> -- ...`), which is a child
subreaper: the game, Proton's wineserver and pressure-vessel stay inside its tree even when they double-fork.
Only that tree is signalled, SIGTERM first and SIGKILL after a short grace; Steam, its web helper, gamescope,
root-owned processes and Panel's own ancestry are never touched, wherever they appear.
"""

import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path

TERM_GRACE_S = 3.0
KILL_GRACE_S = 2.0
POLL_S = 0.1
MAX_APPID = 0xFFFFFFFF

PROTECTED_NAMES = frozenset({
    "steam", "steamwebhelper", "steam-runtime-l", "gamescope", "gamescope-wl", "gamescopereaper",
    "systemd", "plugin_loader", "pluginloader", "plasmashell", "kwin_wayland", "kwin_x11",
})


@dataclass(frozen=True)
class Process:
    pid: int
    ppid: int
    uid: int
    name: str
    state: str
    start: int
    argv: tuple[str, ...]


def normalize_appid(value: object) -> int | None:
    """Steam app ids, or a shortcut's 64-bit game id (the app id lives in its upper 32 bits)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.isdecimal() and len(value) <= 20:
        number = int(value)
    else:
        return None
    if number > MAX_APPID:
        number >>= 32
    return number if 0 < number <= MAX_APPID else None


def _read(proc_root: Path, pid: int) -> Process | None:
    base = proc_root / str(pid)
    try:
        stat = (base / "stat").read_text(errors="replace")
        uid = _status_uid(base / "status")
        argv = (base / "cmdline").read_bytes()[: 64 * 1024]
    except OSError:
        return None
    # comm sits between the first "(" and the last ")"; it may itself contain spaces or parentheses.
    head, _, rest = stat.rpartition(")")
    fields = rest.split()
    if "(" not in head or len(fields) < 20:
        return None
    try:
        ppid = int(fields[1])
        start = int(fields[19])
    except ValueError:
        return None
    return Process(
        pid=pid,
        ppid=ppid,
        uid=uid,
        name=head.split("(", 1)[1][:32].lower(),
        state=fields[0],
        start=start,
        argv=tuple(part.decode("utf-8", "replace") for part in argv.split(b"\0") if part),
    )


def _status_uid(path: Path) -> int:
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("Uid:"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                break
    raise OSError("no uid")


def process_table(proc_root: str | os.PathLike[str] = "/proc") -> dict[int, Process]:
    root = Path(proc_root)
    table: dict[int, Process] = {}
    try:
        entries = list(root.iterdir())
    except OSError:
        return table
    for entry in entries:
        if entry.name.isdecimal():
            process = _read(root, int(entry.name))
            if process is not None:
                table[process.pid] = process
    return table


def _is_reaper_for(process: Process, appid: int) -> bool:
    if process.name != "reaper" and not (process.argv and os.path.basename(process.argv[0]) == "reaper"):
        return False
    marker = f"AppId={appid}"
    # Arguments after "--" are the game's own; only the reaper's options identify it.
    options = process.argv[: process.argv.index("--")] if "--" in process.argv else process.argv
    return marker in options


def protected_pids(table: dict[int, Process], own_pid: int) -> set[int]:
    protected = {0, 1, own_pid}
    pid = own_pid
    while pid in table and table[pid].ppid not in protected:
        pid = table[pid].ppid
        protected.add(pid)
    protected.update(process.pid for process in table.values() if process.name in PROTECTED_NAMES)
    return protected


def _subtree(
    table: dict[int, Process], roots: list[Process], owners: set[int], own_pid: int | None,
) -> list[Process]:
    protected = protected_pids(table, os.getpid() if own_pid is None else own_pid)
    children: dict[int, list[Process]] = {}
    for process in table.values():
        children.setdefault(process.ppid, []).append(process)
    tree: dict[int, Process] = {}
    pending = list(roots)
    while pending:
        process = pending.pop()
        if process.pid in tree:
            continue
        tree[process.pid] = process
        pending.extend(children.get(process.pid, ()))
    return sorted(
        (process for process in tree.values()
         if process.pid not in protected and process.uid in owners and process.uid != 0),
        key=lambda process: process.pid,
    )


def game_tree(table: dict[int, Process], appid: int, own_pid: int | None = None) -> list[Process]:
    """The reaper(s) for this app id and every descendant, minus anything protected."""
    roots = [process for process in table.values() if _is_reaper_for(process, appid) and process.uid != 0]
    return _subtree(table, roots, {root.uid for root in roots}, own_pid) if roots else []


def _alive(proc_root: Path, process: Process) -> bool:
    current = _read(proc_root, process.pid)
    # Same pid and start time is the same process; a zombie is already dead and cannot be signalled.
    return current is not None and current.start == process.start and current.state != "Z"


def force_close(
    appid: object,
    *,
    proc_root: str | os.PathLike[str] = "/proc",
    own_pid: int | None = None,
    kill=os.kill,
    sleep=time.sleep,
    clock=time.monotonic,
    term_grace: float = TERM_GRACE_S,
    kill_grace: float = KILL_GRACE_S,
) -> dict[str, object]:
    number = normalize_appid(appid)
    if number is None:
        return {"result": "failed", "code": "invalid_appid"}
    root = Path(proc_root)

    def find() -> list[Process]:
        return game_tree(process_table(root), number, own_pid)

    def signal_all(processes: list[Process], signum: int) -> None:
        for process in processes:
            if not _alive(root, process):
                continue
            try:
                kill(process.pid, signum)
            except (ProcessLookupError, PermissionError):
                continue

    def wait(processes: list[Process], grace: float) -> list[Process]:
        deadline = clock() + grace
        remaining = [process for process in processes if _alive(root, process)]
        while remaining and clock() < deadline:
            sleep(POLL_S)
            remaining = [process for process in remaining if _alive(root, process)]
        return remaining

    tree = find()
    if not tree:
        return {"result": "not_found", "appid": number}
    signal_all(tree, signal.SIGTERM)
    remaining = wait(tree, term_grace)
    # Anything the game spawned while shutting down goes too: still under the reaper, or, if the reaper
    # already exited, under a survivor of the original tree.
    table = process_table(root)
    survivors = [table[process.pid] for process in remaining if table.get(process.pid, process).start == process.start and process.pid in table]
    owners = {process.uid for process in tree}
    known = {process.pid for process in remaining}
    for process in find() + _subtree(table, survivors, owners, own_pid):
        if process.pid not in known:
            known.add(process.pid)
            remaining.append(process)
    if not remaining:
        return {"result": "terminated", "appid": number, "processes": len(tree)}
    signal_all(remaining, signal.SIGKILL)
    left = wait(remaining, kill_grace)
    if left:
        return {
            "result": "failed",
            "appid": number,
            "processes": len(tree),
            "remaining": [process.name for process in left][:8],
        }
    return {"result": "killed", "appid": number, "processes": len(tree), "killed": len(remaining)}
