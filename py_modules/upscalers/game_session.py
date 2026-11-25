"""One record per game session: how long it lasted and which injections were active when it started.

Reports such as "the game does not start with any scaler" carry no launch outcome: Steam only exposes the running
app id. A session that ends within SHORT_SESSION_S while Mako, Lossless Scaling or OptiScaler were active is the
signal to read next to the per-engine state; the process probe says whether a game process ever existed.
"""

import threading
import time

SHORT_SESSION_S = 90
PROBE_DELAY_S = 20
MAX_PROCESS_NAMES = 10
_QUIET = frozenset({"reaper", "bwrap", "pv-adverb", "pressure-vessel", "wineserver", "services.exe", "winedevice.exe",
                    "plugplay.exe", "svchost.exe", "rpcss.exe", "conhost.exe", "explorer.exe", "tabtip.exe", "steam.exe",
                    "steamwebhelper.exe", "start.exe", "wine", "wine64", "wine-preloader", "wine64-preloader"})


def process_summary(table, appid, game_tree):
    """Whether Steam's reaper for the game exists and which non-infrastructure processes sit under it."""
    from game_force_close import is_reaper_for, normalize_appid
    number = normalize_appid(appid)
    if number is None:
        return {"reaper": False, "processes": 0, "names": []}
    tree = game_tree(table, number)
    reaper = any(is_reaper_for(process, number) for process in tree)
    names = []
    for process in tree:
        name = process.name[:32]
        if name not in _QUIET and name not in names and len(names) < MAX_PROCESS_NAMES:
            names.append(name)
    return {"reaper": reaper, "processes": len(tree), "names": names}


class GameSessions:
    def __init__(self, *, injections, runtime, probe, emit, submit, submit_later,
                 clock=time.monotonic, wall=time.time):
        self._injections = injections
        self._runtime = runtime
        self._probe = probe
        self._emit = emit
        self._submit = submit
        self._submit_later = submit_later
        self._clock = clock
        self._wall = wall
        self._lock = threading.Lock()
        self._session = None

    def transition(self, previous, current):
        if previous == current:
            return
        with self._lock:
            ended, self._session = self._session, None
            if current is not None:
                self._session = {"appid": str(current), "started": self._clock(), "started_at": self._wall(),
                                 "injections": None, "process": None, "probed": False}
                started = self._session
        if ended is not None:
            self._submit(lambda: self._finish(ended))
        if current is not None:
            self._submit(lambda: self._capture(started))
            self._submit_later(PROBE_DELAY_S, lambda: self._sample(started))

    def _capture(self, session):
        try:
            session["injections"] = self._injections(session["appid"])
        except Exception as error:  # noqa: BLE001 — a missing snapshot must not hide the session itself
            session["injections"] = {"error": type(error).__name__}

    def _sample(self, session):
        with self._lock:
            if self._session is not session:
                return
        try:
            session["process"] = self._probe(session["appid"])
        except Exception as error:  # noqa: BLE001
            session["process"] = {"error": type(error).__name__}
        session["probed"] = True

    def _finish(self, session):
        seconds = round(self._clock() - session["started"], 1)
        try:
            runtime = self._runtime(session["appid"])
        except Exception as error:  # noqa: BLE001
            runtime = {"error": type(error).__name__}
        self._emit({
            "appid": session["appid"], "seconds": seconds,
            "outcome": "short" if seconds < SHORT_SESSION_S else "normal",
            "injections": session["injections"] or {},
            "process": session["process"] if session["probed"] else "not_sampled",
            "mako_runtime": runtime,
        })
