import copy
import json
import statistics
import time

from json_store import atomic_json_save


class AutoTdpLearningStore:
    def __init__(
        self,
        path,
        required_samples=12,
        max_samples=48,
        max_profiles=64,
        clock=time.time,
    ):
        self._path = path
        self._required_samples = max(1, int(required_samples))
        self._max_samples = max(self._required_samples, int(max_samples))
        self._max_profiles = max(1, int(max_profiles))
        self._clock = clock
        self._load_status = "missing"
        self._last_record = None
        self._data = self._load()

    def _load(self):
        try:
            with open(self._path) as stream:
                raw = json.load(stream)
        except FileNotFoundError:
            self._load_status = "missing"
            raw = {}
        except OSError:
            self._load_status = "unreadable"
            raw = {}
        except ValueError:
            self._load_status = "invalid"
            raw = {}
        else:
            self._load_status = "ok" if isinstance(raw, dict) else "invalid"
        profiles = raw.get("profiles") if isinstance(raw, dict) else None
        if not isinstance(profiles, dict):
            profiles = {}
        cleaned = {}
        for key, value in profiles.items():
            if not isinstance(value, dict):
                continue
            samples = []
            for sample in value.get("samples", []):
                try:
                    watts = int(
                        sample.get("watts") if isinstance(sample, dict) else sample
                    )
                    at = float(sample.get("at", 0)) if isinstance(sample, dict) else 0.0
                except (TypeError, ValueError, OverflowError):
                    continue
                if watts > 0:
                    samples.append({"watts": watts, "at": max(0.0, at)})
            if samples:
                kept = samples[-self._max_samples:]
                cleaned[str(key)] = {
                    "samples": kept,
                    "updated_at": max(sample["at"] for sample in kept),
                }
        ordered = sorted(
            cleaned.items(),
            key=lambda item: item[1]["updated_at"],
            reverse=True,
        )[:self._max_profiles]
        return {"version": 2, "profiles": dict(ordered)}

    @staticmethod
    def _key(appid, target_fps, on_ac):
        source = "ac" if on_ac else "battery"
        return f"{str(appid)}:{int(target_fps)}:{source}"

    def record(self, appid, target_fps, on_ac, setpoint, *, stable):
        if appid is None or not stable:
            self._last_record = {"ok": False, "reason": "not_eligible"}
            return False
        try:
            watts = int(setpoint)
        except (TypeError, ValueError, OverflowError):
            self._last_record = {"ok": False, "reason": "invalid_setpoint"}
            return False
        if watts <= 0:
            self._last_record = {"ok": False, "reason": "invalid_setpoint"}
            return False
        key = self._key(appid, target_fps, on_ac)
        now = float(self._clock())
        candidate = copy.deepcopy(self._data)
        profile = candidate["profiles"].setdefault(
            key,
            {"samples": [], "updated_at": now},
        )
        profile["samples"].append({"watts": watts, "at": now})
        del profile["samples"][:-self._max_samples]
        profile["updated_at"] = now
        while len(candidate["profiles"]) > self._max_profiles:
            oldest = min(
                candidate["profiles"],
                key=lambda profile_key: candidate["profiles"][profile_key].get(
                    "updated_at", 0
                ),
            )
            del candidate["profiles"][oldest]
        try:
            atomic_json_save(self._path, candidate)
        except OSError:
            self._last_record = {"ok": False, "reason": "persist_failed"}
            return False
        self._data = candidate
        self._load_status = "ok"
        self._last_record = {"ok": True, "reason": "saved"}
        return True

    def seed(self, appid, target_fps, on_ac, min_w, max_w):
        if appid is None:
            return None
        profile = self._data["profiles"].get(
            self._key(appid, target_fps, on_ac)
        )
        samples = profile.get("samples", []) if isinstance(profile, dict) else []
        if len(samples) < self._required_samples:
            return None
        watts = int(statistics.median_low(sample["watts"] for sample in samples))
        minimum = int(min_w)
        maximum = max(minimum, int(max_w))
        return {
            "watts": max(minimum, min(watts, maximum)),
            "samples": len(samples),
            "confidence": min(
                1.0,
                (len(samples) - self._required_samples + 1)
                / self._required_samples,
            ),
        }

    def reset(self):
        self._data = {"version": 2, "profiles": {}}
        atomic_json_save(self._path, self._data)
        self._load_status = "ok"
        self._last_record = {"ok": True, "reason": "reset"}

    def diagnostics(self, appid, target_fps, on_ac, min_w, max_w):
        profile = self._data["profiles"].get(
            self._key(appid, target_fps, on_ac)
        ) if appid is not None else None
        samples = profile.get("samples", []) if isinstance(profile, dict) else []
        candidate = self.seed(appid, target_fps, on_ac, min_w, max_w)
        return {
            "load_status": self._load_status,
            "profiles": len(self._data["profiles"]),
            "samples": len(samples),
            "required_samples": self._required_samples,
            "usable": candidate is not None,
            "candidate_watts": (
                candidate["watts"] if candidate is not None else None
            ),
            "confidence": (
                candidate["confidence"] if candidate is not None else None
            ),
            "last_record": (
                dict(self._last_record) if self._last_record is not None else None
            ),
        }
