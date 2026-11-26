"""One record per game session: its duration and the injections active when it started.

An outcome (short/normal) is only claimed for sessions whose start Panel observed as a launch; a game already running
when Panel loaded, or a context set by a profile editor, is "attached" with no outcome.
"""

import threading
import time

SHORT_SESSION_S = 90
PROBE_DELAYS_S = (5, 20)
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

    def transition(self, previous, current, launch=False):
        if previous == current:
            return
        now = self._clock()
        with self._lock:
            ended, self._session = self._session, None
            started = None
            if current is not None:
                started = self._session = {
                    "appid": str(current), "started": now, "start": "launch" if launch else "attached",
                    "injections": None, "reason": "not_captured", "probes": [], "timers": []}
        if ended is not None:
            self._cancel(ended)
            ended["ended"], ended["ended_by"] = now, "game_stopped" if current is None else "context_change"
            self._submit(lambda: self._finish(ended))
        if started is not None:
            self._submit(lambda: self._capture(started))
            for delay in PROBE_DELAYS_S:
                timer = self._submit_later(delay, lambda delay=delay: self._sample(started, delay))
                started["timers"].append(timer)

    def close(self):
        """Emit the open session without blocking: plugin unload must not lose it nor wait for probes."""
        with self._lock:
            ended, self._session = self._session, None
        if ended is None:
            return
        self._cancel(ended)
        ended["ended"], ended["ended_by"] = self._clock(), "plugin_unload"
        self._emit(self._record(ended, "not_collected"))

    @staticmethod
    def _cancel(session):
        for timer in session["timers"]:
            cancel = getattr(timer, "cancel", None)
            if cancel is not None:
                cancel()

    def _capture(self, session):
        try:
            found = self._injections(session["appid"])
        except Exception as error:  # noqa: BLE001 — a missing snapshot must not hide the session itself
            session["injections"], session["reason"] = None, "error:" + type(error).__name__
            return
        if found is None:
            session["injections"], session["reason"] = None, "service_unavailable"
        else:
            session["injections"], session["reason"] = found, None

    def _probe_once(self, session, label):
        try:
            sample = self._probe(session["appid"])
        except Exception as error:  # noqa: BLE001
            sample = {"error": type(error).__name__}
        session["probes"].append({"at": label} | sample)

    def _sample(self, session, delay):
        with self._lock:
            if self._session is not session:
                return
        self._probe_once(session, delay)

    def _finish(self, session):
        if not session["probes"]:
            self._probe_once(session, "finish")
        try:
            runtime = self._runtime(session["appid"])
        except Exception as error:  # noqa: BLE001
            runtime = {"error": type(error).__name__}
        self._emit(self._record(session, runtime))

    def _record(self, session, runtime):
        seconds = round(session["ended"] - session["started"], 1)
        record = {
            "appid": session["appid"], "seconds": seconds, "start": session["start"],
            "ended_by": session["ended_by"],
            "injections": session["injections"], "process": session["probes"] or "not_sampled",
            "mako_runtime": runtime,
        }
        if session["injections"] is None:
            record["injections_reason"] = session["reason"]
        if session["start"] == "launch":
            record["outcome"] = "short" if seconds < SHORT_SESSION_S else "normal"
        return record
