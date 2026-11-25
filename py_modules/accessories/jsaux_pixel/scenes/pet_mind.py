"""The pet's inner life.

Needs drift with real time and only care restores them; a personality is drawn once at birth;
memories record how it is treated and what gets played, so scary games frighten it less with
practice and the most played genre becomes its favourite. A utility brain plans what it does next
from all of that. Planning is a pure function of the memory: the scene can rehearse ten minutes
of life in advance and write them to the panel as one GIF.
"""

import json
import random
import threading
import time
from collections.abc import Callable
from pathlib import Path

from json_store import atomic_json_save

TRAITS = ("brave", "playful", "greedy", "sleepy", "curious")
_HUNGER_S = 8 * 3600
_AWAKE_S = 16 * 3600
# Memory keys that start as None: their stored type cannot be read off the default.
_NULLABLE = {"asleep_since": (int, float), "proud_at": (int, float), "last_session": str, "interaction": list}
_SLEEP_RECOVERY_S = 7 * 3600
_FUN_S = 5 * 3600
_LOVE_S = 20 * 3600
_FULL = 0.8
_PLAY_REFRESH_S = 600
_NAME_MAX = 15
_WEEK_HOURS = 7 * 24
_HABIT_HALF_LIFE_S = 14 * 86400
_HABIT_MIN_TOTAL = 60.0
_HABIT_FULL_WEEKLY = 40.0
_HABIT_FULL_DAILY = 120.0
_TICK_CAP_S = 10.0
_ABSENT_S = 1800.0
_SEEN_SAVE_S = 600.0
# While asleep the belly empties at half speed, affection fades at three quarters and fun holds.
_SLEEP_DRIFT = {"fed_at": 0.5, "fun_at": 1.0, "petted_at": 0.25}
DEFAULT_NAME = "Pixi"

# Steam store tag ids, matched in the order the store ranks a game's tags.
_GENRE_TAGS = {
    1667: "horror", 3978: "horror", 1721: "horror", 4255: "horror",
    699: "racing", 1644: "racing",
    1774: "shooter", 1663: "shooter", 3814: "shooter",
    122: "rpg", 4434: "rpg", 21: "rpg",
    1664: "puzzle", 9: "puzzle",
    1625: "platformer",
    1743: "fighting",
    701: "sports",
    1752: "rhythm",
    29482: "souls", 4026: "souls",
    4726: "cozy", 1654: "cozy", 597: "cozy",
}
_GENRE_ACTION = {
    "horror": "shiver", "racing": "zoom", "shooter": "aim", "rpg": "sword", "puzzle": "think",
    "platformer": "hop", "fighting": "box", "sports": "ball", "rhythm": "dance", "souls": "sweat", "cozy": "hearts",
}


def genre_for(tags) -> str | None:
    for tag in tags or ():
        genre = _GENRE_TAGS.get(tag if isinstance(tag, int) else -1)
        if genre:
            return genre
    return None


def genre_action(genre: str | None) -> str | None:
    return _GENRE_ACTION.get(genre or "")


# name: (where it can happen, seconds it lasts)
ACTIONS: dict[str, tuple[frozenset, float]] = {
    name: (frozenset(places.split()), seconds)
    for name, places, seconds in (
        ("hop", "home game", 1.5), ("dance", "home game", 1.5), ("wander", "home", 2.0), ("stars", "home", 1.5),
        ("ball", "home game", 1.2), ("butterfly", "home", 1.7), ("peekaboo", "home", 2.0), ("hearts", "home game", 1.2),
        ("wave", "home", 1.0), ("sneeze", "home", 0.7), ("nap", "home", 1.4), ("snack", "home", 1.4),
        ("hungry", "home game", 1.6), ("yawn", "home game", 1.2), ("call", "home", 1.8), ("sulk", "home", 2.0),
        ("explore", "home", 2.0), ("watch", "game", 2.0), ("cheer", "game", 1.2), ("shiver", "game", 1.6),
        ("zoom", "game", 1.4), ("aim", "game", 1.6), ("sword", "game", 1.4), ("think", "game", 1.8),
        ("box", "game", 1.2), ("sweat", "game hot", 1.4), ("fan_self", "hot", 1.6), ("blown", "windy", 2.4),
        ("hold", "windy", 1.6), ("await", "home", 2.0), ("impatient", "home", 1.6), ("dream", "night", 2.4), ("turn", "night", 1.2), ("snore", "night", 1.6),
    )
}
_PLAYFUL = ("hop", "dance", "stars", "ball", "butterfly", "peekaboo", "wave")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _urgency(value: float) -> float:
    return (1.0 - value) ** 2


class Mind:
    def __init__(self, path: Path | str | None, clock: Callable[[], float] = time.time,
                 rng: random.Random | None = None):
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        stored = self._load()
        now = clock()
        rng = rng or random.Random()
        traits = stored.get("traits") if isinstance(stored.get("traits"), dict) else {}
        if set(traits) != set(TRAITS) or not all(isinstance(v, (int, float)) for v in traits.values()):
            traits = {trait: round(rng.uniform(0.15, 0.95), 2) for trait in TRAITS}
        self.traits: dict[str, float] = traits
        memory = stored.get("memory") if isinstance(stored.get("memory"), dict) else {}
        self.memory: dict = {
            "name": DEFAULT_NAME, "born_at": now, "fed_at": now, "fun_at": now, "petted_at": now,
            "woke_at": now, "energy_base": 1.0, "asleep_since": None, "genres": {}, "last_session": None,
            "achievements": 0, "proud_at": None, "interaction": None, "revision": 0,
            "routine": [0.0] * _WEEK_HOURS, "routine_at": now, "seen_at": now,
        }
        for key, value in memory.items():
            if key not in self.memory:
                continue
            kind = _NULLABLE.get(key)
            default = self.memory[key]
            if value is None or (isinstance(value, kind) if kind else (isinstance(value, type(default)) or
                                 isinstance(value, (int, float)) and isinstance(default, (int, float)))):
                self.memory[key] = value
        routine = self.memory["routine"]
        if len(routine) != _WEEK_HOURS or not all(isinstance(v, (int, float)) and v >= 0 for v in routine):
            self.memory["routine"] = [0.0] * _WEEK_HOURS
        self._pending: dict[int, float] = {}
        self._play_tick: float | None = None
        self._seen_saved = self.memory["seen_at"]
        if not stored:
            self._save()

    def _load(self) -> dict:
        if self._path is None:
            return {}
        try:
            data = json.loads(self._path.read_text())
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            atomic_json_save(str(self._path), {"traits": self.traits, "memory": self.memory})
        except OSError:
            pass

    # Needs ----------------------------------------------------------------------------------

    def needs(self, now: float) -> dict[str, float]:
        m = self.memory
        return {
            "hunger": _clamp(1 - (now - m["fed_at"]) / _HUNGER_S),
            "energy": self._energy(now),
            "fun": _clamp(1 - (now - m["fun_at"]) / _FUN_S),
            "love": _clamp(1 - (now - m["petted_at"]) / _LOVE_S),
        }

    def _energy(self, now: float) -> float:
        m = self.memory
        asleep = m["asleep_since"]
        if asleep is not None:
            at_sleep = _clamp(m["energy_base"] - (asleep - m["woke_at"]) / _AWAKE_S)
            return _clamp(at_sleep + (now - asleep) / _SLEEP_RECOVERY_S)
        return _clamp(m["energy_base"] - (now - m["woke_at"]) / _AWAKE_S)

    def asleep(self) -> bool:
        return self.memory["asleep_since"] is not None

    # Things that happen to it ---------------------------------------------------------------

    def interact(self, kind: str, now: float) -> str:
        with self._lock:
            needs = self.needs(now)
            if kind == "feed":
                reaction = "refuse" if needs["hunger"] >= _FULL else "eat"
                if reaction == "eat":
                    self.memory["fed_at"] = now
            elif kind == "play":
                reaction = "tired" if needs["energy"] < 0.15 else "play"
                if reaction == "play":
                    self.memory["fun_at"] = now
                    self._spend_energy(now, 0.05)
            elif kind == "pet":
                reaction = "purr"
                self.memory["petted_at"] = now
            elif kind == "sleep":
                reaction = "sleep" if not self.asleep() else "snore"
                self._fall_asleep(now)
            elif kind == "wake":
                reaction = "wake"
                self._wake(now)
            else:
                raise ValueError(f"unknown interaction {kind!r}")
            self._remember(now, reaction)
            return reaction

    def observe(self, now: float, *, night: bool, playing: bool, hour_of_week: int | None = None) -> None:
        """Called on every tick: night puts it to bed, morning wakes it, play keeps it amused, and the
        hours you play are learnt (saved together with the play refresh, every ten minutes)."""
        with self._lock:
            changed = False
            if now - self.memory["seen_at"] > _ABSENT_S and not self.asleep():
                # The console was off or suspended: the pet slept with it.
                self.memory["asleep_since"] = self.memory["seen_at"]
                changed = True
            self.memory["seen_at"] = now
            if now - self._seen_saved >= _SEEN_SAVE_S:
                changed = True
            if playing and hour_of_week is not None and 0 <= hour_of_week < _WEEK_HOURS:
                if self._play_tick is not None:
                    minutes = min(_TICK_CAP_S, max(0.0, now - self._play_tick)) / 60
                    self._pending[hour_of_week] = self._pending.get(hour_of_week, 0.0) + minutes
                self._play_tick = now
            else:
                self._play_tick = None
                if self._pending:
                    self._learn(now)
                    changed = True
            if night and not playing and not self.asleep():
                self._fall_asleep(now)
                changed = True
            elif not night and self.asleep() and self._energy(now) >= 0.95:
                self._wake(now)
                changed = True
            elif playing and self.asleep():
                self._wake(now)
                changed = True
            if playing and now - self.memory["fun_at"] >= _PLAY_REFRESH_S:
                self.memory["fun_at"] = now
                self._learn(now)
                changed = True
            if changed:
                self._seen_saved = now
                self._save()

    def _learn(self, now: float) -> None:
        self.memory["routine"] = [w + self._pending.get(h, 0.0) for h, w in enumerate(self._routine(now))]
        self.memory["routine_at"] = now
        self._pending = {}

    def _routine(self, now: float) -> list[float]:
        """Minutes played per hour of the week, fading with a two-week half-life so habits change."""
        fade = 0.5 ** (max(0.0, now - self.memory["routine_at"]) / _HABIT_HALF_LIFE_S)
        return [w * fade for w in self.memory["routine"]]

    def _weights(self, now: float) -> list[float]:
        return [w + self._pending.get(h, 0.0) for h, w in enumerate(self._routine(now))]

    def expectation(self, hour_of_week: int, now: float) -> float:
        """How sure it is that you come to play at this hour: 0 until a real habit exists."""
        weights = self._weights(now)
        if sum(weights) < _HABIT_MIN_TOTAL:
            return 0.0
        hour = hour_of_week % 24
        daily = sum(weights[day * 24 + hour] for day in range(7))
        return round(min(1.0, max(weights[hour_of_week % _WEEK_HOURS] / _HABIT_FULL_WEEKLY, daily / _HABIT_FULL_DAILY)), 3)

    def usual_hours(self, now: float) -> list[int] | None:
        weights = self._weights(now)
        if sum(weights) < _HABIT_MIN_TOTAL:
            return None
        daily = [sum(weights[day * 24 + hour] for day in range(7)) for hour in range(24)]
        peak = max(range(24), key=lambda h: daily[h])
        start = end = peak
        while daily[(start - 1) % 24] >= daily[peak] / 2 and (start - 1) % 24 != peak:
            start = (start - 1) % 24
        while daily[(end + 1) % 24] >= daily[peak] / 2 and (end + 1) % 24 != start:
            end = (end + 1) % 24
        return [start, (end + 1) % 24]

    def saw_game(self, appid: str, genre: str | None, started_at: float) -> None:
        with self._lock:
            session = f"{appid}:{round(started_at)}"
            if self.memory["last_session"] == session:
                return
            self.memory["last_session"] = session
            if genre:
                genres = dict(self.memory["genres"])
                genres[genre] = genres.get(genre, 0) + 1
                self.memory["genres"] = genres
            self._save()

    def achievement(self, now: float) -> None:
        with self._lock:
            self.memory["achievements"] += 1
            self.memory["proud_at"] = now
            self._remember(now, "trophy")

    def rename(self, name: str) -> None:
        clean = " ".join(str(name or "").split())[:_NAME_MAX].strip()
        if clean:
            with self._lock:
                self.memory["name"] = clean
                self._save()

    def _fall_asleep(self, now: float) -> None:
        if not self.asleep():
            self.memory["asleep_since"] = now

    def _wake(self, now: float) -> None:
        asleep = self.memory["asleep_since"]
        if asleep is not None:
            slept = max(0.0, now - asleep)
            for key, credit in _SLEEP_DRIFT.items():
                self.memory[key] = min(now, self.memory[key] + slept * credit)
        self.memory["energy_base"] = self._energy(now)
        self.memory["woke_at"] = now
        self.memory["asleep_since"] = None

    def _spend_energy(self, now: float, amount: float) -> None:
        if not self.asleep():
            self.memory["energy_base"] = _clamp(self._energy(now) - amount)
            self.memory["woke_at"] = now

    def _remember(self, now: float, reaction: str) -> None:
        self.memory["interaction"] = [reaction, now]
        self.memory["revision"] += 1
        self._save()

    # What it thinks of things ---------------------------------------------------------------

    def fear(self, genre: str | None) -> float:
        if genre != "horror":
            return 0.0
        seen = self.memory["genres"].get("horror", 0)
        return round((1 - self.traits["brave"] * 0.5) * 0.75 ** seen, 3)

    def favourite(self) -> str | None:
        genres = self.memory["genres"]
        return max(genres, key=lambda g: (genres[g], g)) if genres else None

    def recent(self, now: float, window_s: float = 60.0) -> str | None:
        """The reaction to show first, while the care that caused it is still fresh."""
        interaction = self.memory["interaction"]
        if isinstance(interaction, list) and len(interaction) == 2 and 0 <= now - interaction[1] < window_s:
            return interaction[0]
        return None

    def proud(self, now: float) -> bool:
        at = self.memory["proud_at"]
        return isinstance(at, (int, float)) and 0 <= now - at < 900

    def describe(self, now: float) -> dict:
        return {
            "name": self.memory["name"],
            "needs": {key: round(value, 3) for key, value in self.needs(now).items()},
            "traits": dict(self.traits),
            "asleep": self.asleep(),
            "favourite": self.favourite(),
            "age_days": max(0, int((now - self.memory["born_at"]) // 86400)),
            "achievements": self.memory["achievements"],
            "usual_hours": self.usual_hours(now),
        }

    # The brain ------------------------------------------------------------------------------

    def plan(self, now: float, seconds: float, *, situation: str, rng: random.Random,
             expect: float = 0.0) -> list[tuple[str, float]]:
        """(action, seconds of rest before it) filling `seconds`, chosen by what it needs and is."""
        place, _, genre = situation.partition(":")
        needs = self.needs(now)
        traits = self.traits
        proud = self.proud(now)
        plan: list[tuple[str, float]] = []
        used = 0.0
        while True:
            options = {name: self._score(name, place, genre, needs, traits, proud, expect)
                       for name, (places, _length) in ACTIONS.items() if place in places}
            for name in [p for p, _ in plan[-3:]]:
                if name in options:
                    options[name] -= 0.45
            if plan:
                options.pop(plan[-1][0], None)
            options = {name: score + rng.uniform(0, 0.5) for name, score in options.items() if score > -0.5}
            if not options:
                break
            name = max(options, key=lambda n: (options[n], n))
            if place == "night":
                rest = 0.5 if not plan else rng.uniform(18, 50)
            else:
                rest = 0.5 if not plan else rng.uniform(5, 16) * (0.7 + (1 - needs["energy"]) * 0.8)
            length = ACTIONS[name][1]
            if used + rest + length > seconds:
                break
            plan.append((name, round(rest, 2)))
            used += rest + length
            needs = _after(name, needs)
        return plan

    def _score(self, name: str, place: str, genre: str, needs: dict, traits: dict, proud: bool, expect: float = 0.0) -> float:
        hunger, energy, fun, love = needs["hunger"], needs["energy"], needs["fun"], needs["love"]
        if place == "night":
            return {"dream": 1.0 + traits["curious"] * 0.3, "snore": 0.8 + traits["sleepy"] * 0.5, "turn": 0.6}[name]
        if place == "windy":
            return {"blown": 1.2 + (1 - traits["brave"]) * 0.4, "hold": 0.9 + traits["brave"] * 0.5}[name]
        if place == "hot":
            return {"fan_self": 1.1, "sweat": 1.0}[name]
        if name == "snack":
            return 3.0 * _urgency(hunger) + traits["greedy"] * 0.4 if hunger < 0.4 else -1
        if name == "hungry":
            return 2.2 * _urgency(hunger) if hunger < 0.5 else -1
        if name == "nap":
            return 2.5 * _urgency(energy) + traits["sleepy"] * 0.3 if energy < 0.45 else -1
        if name == "yawn":
            return 1.6 * _urgency(energy) + traits["sleepy"] * 0.2 if energy < 0.6 else -1
        if name == "call":
            return 2.6 * _urgency(love) if love < 0.5 else -1
        if name == "sulk":
            return 3.0 * _urgency(love) if love < 0.25 else -1
        if name == "sneeze":
            return 0.15
        if name == "await":
            return 2.4 * expect + traits["playful"] * 0.3 if expect >= 0.5 else -1
        if name == "impatient":
            return 1.8 * expect + (1 - fun) * 0.5 if expect >= 0.7 and fun < 0.7 else -1
        if name in ("wander", "explore"):
            return 0.5 + traits["curious"] * 0.6
        if place == "game":
            if name == "watch":
                return 1.0
            if name == "cheer":
                return 0.6 + traits["playful"] * 0.3 + (0.9 if proud else 0)
            if name == "shiver":
                return (0.6 + self.fear("horror") * 1.2) if genre == "horror" else -1
            if name == genre_action(genre):
                return 1.25 + (0.3 if genre == self.favourite() else 0)
            if name in ("hop", "dance", "ball", "hearts"):
                return 0.35 + traits["playful"] * 0.3
            return -1
        if name in _PLAYFUL:
            if energy < 0.25:
                return -1
            return 0.6 + 1.2 * _urgency(fun) + traits["playful"] * 0.4
        if name == "hearts":
            return 0.4 + love * 0.6 + (0.8 if proud else 0)
        return -1


def _after(name: str, needs: dict) -> dict:
    """What the rehearsal assumes an action does, so a planned evening hangs together."""
    hunger, energy, fun, love = needs["hunger"], needs["energy"], needs["fun"], needs["love"]
    if name == "snack":
        hunger = _clamp(hunger + 0.45)
    elif name == "nap":
        energy = _clamp(energy + 0.2)
    elif name in _PLAYFUL:
        fun, energy = _clamp(fun + 0.12), _clamp(energy - 0.03)
    elif name == "call":
        love = _clamp(love + 0.05)
    return {"hunger": hunger, "energy": energy, "fun": fun, "love": love}
