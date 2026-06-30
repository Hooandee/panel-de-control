import json

from json_store import atomic_json_save

_MAX_RECENT = 120
_MAX_GAMES = 50

# Temperature histogram (feeds the F3 suggestion brain): 2 °C bins over 30–100 °C,
# keyed by the driving temp = max(temp_cpu, temp_gpu) per sample.
_TEMP_BIN_WIDTH = 2
_TEMP_BIN_MIN = 30
_TEMP_BIN_MAX = 98  # last bin lower-bound (covers 98–100+)


def _temp_bin(temp: float) -> int:
    """Floor *temp* to its 2 °C bin lower-bound, clamped to [30, 98]."""
    b = int(temp // _TEMP_BIN_WIDTH) * _TEMP_BIN_WIDTH
    return max(_TEMP_BIN_MIN, min(_TEMP_BIN_MAX, b))

_METRICS = (
    # (bin_key, sample_key, avg_key)
    ("watts", "watts", "watts_avg"),
    ("gpu", "gpu_busy", "gpu_avg"),
    ("t_cpu", "temp_cpu", "temp_cpu_avg"),
    ("t_gpu", "temp_gpu", "temp_gpu_avg"),
    ("rpm", "fan_rpm", "rpm_avg"),
)


class TelemetryStore:
    """Aggregated per-game telemetry: bins by sustained pl1, ring of recent samples.

    Never raises. Persists atomically via atomic_json_save. The internal JSON
    shape mirrors the public aggregate() output closely so reload is cheap.

    Internal structure::

        {
          "games": {
            "<appid>": {
              "n": int,
              "last_ts": float,
              "by_pl1": {
                "<pl1 str>": {
                  "seconds": float,
                  "watts":  {"sum": float, "n": int},
                  "gpu":    {"sum": float, "n": int},
                  "t_cpu":  {"sum": float, "n": int},
                  "t_gpu":  {"sum": float, "n": int},
                  "rpm":    {"sum": float, "n": int},
                }
              },
              "recent": [{"ts", "pl1", "watts", "gpu", "t_cpu", "t_gpu", "rpm"}, ...]
            }
          }
        }
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._data = self._load()
        self._dirty = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_sample(self, appid: str, sample: dict, dt: float = 5.0, ts: float = 0) -> None:
        """Record one sample for *appid*.

        *sample* keys: pl1(int), watts, gpu_busy, temp_cpu, temp_gpu, fan_rpm.
        Any metric may be None; missing keys are treated as None.
        Never raises.
        """
        try:
            self._add(str(appid), sample, float(dt), float(ts))
            self._trim_games()
            # Buffer in memory; persistence is throttled via flush() (called on a
            # slower cadence + on stop) to spare the eMMC from a write every 5 s.
            self._dirty = True
        except Exception:  # noqa: BLE001
            pass

    def aggregate(self, appid: str) -> dict:
        """Return aggregated stats for *appid*.

        Each *_avg key is None when no valid samples were recorded for that
        metric (honest — never a fake zero).

        Returns ``{"samples_n": 0, "by_pl1": {}, "recent": []}`` for an
        unknown appid.
        """
        game = self._data["games"].get(str(appid))
        if game is None:
            return {"samples_n": 0, "by_pl1": {}, "recent": []}

        by_pl1 = {}
        for pl1_str, bin_ in game["by_pl1"].items():
            row = {"seconds": bin_["seconds"]}
            for bin_key, _sample_key, avg_key in _METRICS:
                acc = bin_.get(bin_key, {"sum": 0.0, "n": 0})
                row[avg_key] = (acc["sum"] / acc["n"]) if acc["n"] > 0 else None
            by_pl1[int(pl1_str)] = row

        return {
            "samples_n": game["n"],
            "by_pl1": by_pl1,
            "recent": list(game["recent"]),
        }

    def temp_histogram(self, appid: str) -> dict:
        """Return ``{bin_lower_temp(int): seconds(float)}`` for *appid*.

        Bins are 2 °C wide over 30–100 °C, keyed by the driving temp
        (max of cpu/gpu) per sample. Empty dict for an unknown appid.
        """
        game = self._data["games"].get(str(appid))
        if game is None:
            return {}
        return {int(k): float(v) for k, v in game["temp_hist"].items()}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add(self, appid: str, sample: dict, dt: float, ts: float) -> None:
        try:
            pl1 = int(sample["pl1"])
        except (KeyError, TypeError, ValueError):
            pl1 = 0

        game = self._data["games"].setdefault(appid, _empty_game())
        game["n"] += 1
        game["last_ts"] = ts

        pl1_key = str(pl1)
        bin_ = game["by_pl1"].setdefault(pl1_key, _empty_bin())
        bin_["seconds"] += dt

        for bin_key, sample_key, _avg_key in _METRICS:
            val = sample.get(sample_key)
            if val is not None:
                acc = bin_[bin_key]
                acc["sum"] += float(val)
                acc["n"] += 1

        entry = {
            "ts": ts,
            "pl1": pl1,
            "watts": sample.get("watts"),
            "gpu": sample.get("gpu_busy"),
            "t_cpu": sample.get("temp_cpu"),
            "t_gpu": sample.get("temp_gpu"),
            "rpm": sample.get("fan_rpm"),
        }
        recent = game["recent"]
        recent.append(entry)
        if len(recent) > _MAX_RECENT:
            game["recent"] = recent[-_MAX_RECENT:]

        # Temperature histogram: accumulate dwell seconds in the driving-temp bin.
        cpu, gpu = sample.get("temp_cpu"), sample.get("temp_gpu")
        present = [float(t) for t in (cpu, gpu) if t is not None]
        if present:
            bin_key = str(_temp_bin(max(present)))
            hist = game["temp_hist"]
            hist[bin_key] = hist.get(bin_key, 0.0) + dt

    def _trim_games(self) -> None:
        games = self._data["games"]
        if len(games) <= _MAX_GAMES:
            return
        # Prune the game with the smallest last_ts (oldest last-updated)
        oldest = min(games, key=lambda k: games[k].get("last_ts", 0.0))
        del games[oldest]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        try:
            with open(self._path) as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raise ValueError("bad root")
            return _clean_root(raw)
        except (OSError, ValueError, KeyError, TypeError):
            return {"games": {}}

    def flush(self) -> None:
        """Persist buffered samples to disk if anything changed. Never raises."""
        if not self._dirty:
            return
        try:
            atomic_json_save(self._path, self._data)
            self._dirty = False
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------
# Factory helpers
# ------------------------------------------------------------------

def _empty_game() -> dict:
    return {"n": 0, "last_ts": 0.0, "by_pl1": {}, "recent": [], "temp_hist": {}}


def _empty_bin() -> dict:
    out: dict = {"seconds": 0.0}
    for bin_key, _sample_key, _avg_key in _METRICS:
        out[bin_key] = {"sum": 0.0, "n": 0}
    return out


def _clean_bin(raw: object) -> dict:
    if not isinstance(raw, dict):
        return _empty_bin()
    out = _empty_bin()
    try:
        out["seconds"] = float(raw.get("seconds", 0.0))
    except (TypeError, ValueError):
        pass
    for key, _sk, _ak in _METRICS:
        acc = raw.get(key)
        if isinstance(acc, dict):
            try:
                out[key] = {"sum": float(acc.get("sum", 0.0)),
                            "n": int(acc.get("n", 0))}
            except (TypeError, ValueError):
                pass
    return out


def _clean_game(raw: object) -> dict:
    if not isinstance(raw, dict):
        return _empty_game()
    game = _empty_game()
    try:
        game["n"] = int(raw.get("n", 0))
    except (TypeError, ValueError):
        pass
    try:
        game["last_ts"] = float(raw.get("last_ts", 0.0))
    except (TypeError, ValueError):
        pass
    raw_bins = raw.get("by_pl1")
    if isinstance(raw_bins, dict):
        for k, v in raw_bins.items():
            try:
                int(k)  # validate key is integer-like
            except (TypeError, ValueError):
                continue
            game["by_pl1"][k] = _clean_bin(v)
    raw_recent = raw.get("recent")
    if isinstance(raw_recent, list):
        game["recent"] = raw_recent[-_MAX_RECENT:]
    raw_hist = raw.get("temp_hist")
    if isinstance(raw_hist, dict):
        for k, v in raw_hist.items():
            try:
                game["temp_hist"][str(int(k))] = float(v)
            except (TypeError, ValueError):
                continue
    return game


def _clean_root(raw: dict) -> dict:
    out: dict = {"games": {}}
    raw_games = raw.get("games")
    if isinstance(raw_games, dict):
        for appid, game_raw in raw_games.items():
            out["games"][str(appid)] = _clean_game(game_raw)
    return out
