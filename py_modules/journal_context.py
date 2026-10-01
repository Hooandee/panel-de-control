"""Plugins, services and machine state around Panel, written only when they change."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Callable

_RIVAL_PLUGINS = {
    "simpledeckytdp": "tdp",
    "powertools": "tdp",
    "powercontrol": "tdp",
    "decktdp": "tdp",
    "tdpcontrol": "tdp",
    "hhddecky": "tdp",
    "handhelddaemon": "tdp",
    "fantastic": "fans",
    "fancontrol": "fans",
}
_POWER_SERVICES = {
    "hhd": "tdp",
    "powerstation": "tdp",
    "power-profiles-daemon": "profile",
    "tuned": "profile",
    "tuned-ppd": "profile",
    "steamos-manager": "tdp",
    "jupiter-fan-control": "fans",
    "fw-fanctrl": "fans",
    "armada-powerd": "tdp",
    "armada-steamos-manager": "tdp",
    "armada-control": "system",
    "inputplumber": "controller",
    "handycon": "controller",
}
_UNIT = re.compile(r"^(?P<stem>[A-Za-z0-9_.-]+?)(?:@[^.\s]*)?\.service$")
_MAX_PLUGINS = 64


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def plugin_inventory(plugins_dir: str, loader_settings: str) -> list[dict]:
    try:
        with open(loader_settings, encoding="utf-8") as handle:
            disabled = set(json.load(handle).get("disabled_plugins") or [])
    except (OSError, ValueError, AttributeError):
        disabled = set()
    plugins = []
    try:
        entries = sorted(os.scandir(plugins_dir), key=lambda entry: entry.name)
    except OSError:
        return plugins
    for entry in entries[:_MAX_PLUGINS]:
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        name = _manifest(entry.path, "plugin.json", "name") or entry.name
        plugins.append({
            "name": name[:80],
            "version": _manifest(entry.path, "package.json", "version"),
            "enabled": name not in disabled,
        })
    return plugins


def _manifest(directory: str, file_name: str, key: str) -> str | None:
    try:
        with open(os.path.join(directory, file_name), encoding="utf-8") as handle:
            value = json.load(handle).get(key)
    except (OSError, ValueError, AttributeError):
        return None
    return value[:80] if isinstance(value, str) else None


def active_services(run: Callable[[list[str]], str | None]) -> list[str]:
    output = run(["systemctl", "list-units", "--type=service", "--state=active", "--no-legend", "--plain"])
    found = set()
    for line in (output or "").splitlines():
        unit = line.split(None, 1)[0] if line.strip() else ""
        match = _UNIT.match(unit)
        if match and match.group("stem") in _POWER_SERVICES:
            found.add(match.group("stem"))
    return sorted(found)


def rivals(plugins: list[dict], services: list[str]) -> list[dict]:
    found = []
    for plugin in plugins:
        area = _RIVAL_PLUGINS.get(_normalise(plugin["name"]))
        if area and plugin.get("enabled", True):
            found.append({"name": plugin["name"], "kind": "plugin", "writes": area})
    for service in services:
        area = _POWER_SERVICES[service]
        if area in ("tdp", "fans", "profile"):
            found.append({"name": service, "kind": "service", "writes": area})
    return found


def context_snapshot(plugins_dir: str, loader_settings: str, run: Callable[[list[str]], str | None]) -> dict:
    plugins = plugin_inventory(plugins_dir, loader_settings)
    services = active_services(run)
    return {"plugins": plugins, "services": services, "rivals": rivals(plugins, services)}


def context_changes(previous: dict | None, current: dict) -> dict | None:
    if previous is None:
        return None
    before = {plugin["name"]: plugin for plugin in previous.get("plugins", [])}
    after = {plugin["name"]: plugin for plugin in current.get("plugins", [])}
    changes = {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "toggled": sorted(
            name for name in set(after) & set(before)
            if after[name].get("enabled") != before[name].get("enabled")
            or after[name].get("version") != before[name].get("version")
        ),
        "services_started": sorted(set(current.get("services", [])) - set(previous.get("services", []))),
        "services_stopped": sorted(set(previous.get("services", [])) - set(current.get("services", []))),
    }
    return {key: value for key, value in changes.items() if value} or None


_ARTWORK = re.compile(r"^\d+(?P<kind>p|_hero|_logo|_icon)?\.(?P<ext>png|jpg|jpeg|webp|ico)$", re.I)
_ARTWORK_KINDS = {"p": "cover", "_hero": "hero", "_logo": "logo", "_icon": "icon", None: "wide"}


def custom_artwork(userdata: str) -> dict:
    """SteamGridDB saves custom art as .png, which Steam tries only after .jpg fails."""
    counts: dict[str, int] = {}
    try:
        users = os.listdir(userdata)
    except OSError:
        return counts
    for user in users[:8]:
        try:
            names = os.listdir(os.path.join(userdata, user, "config", "grid"))
        except OSError:
            continue
        for name in names[:5000]:
            match = _ARTWORK.match(name)
            if match:
                key = f"{_ARTWORK_KINDS[match.group('kind')]}.{match.group('ext').lower()}"
                counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


_MAX_SECTION_JSON = 2000


def pick_fields(value: object, fields: tuple[str, ...] | None) -> object:
    if fields is None or not isinstance(value, dict):
        return value
    picked = {}
    for field in fields:
        current: object = value
        for part in field.split("."):
            if not isinstance(current, dict) or part not in current:
                break
            current = current[part]
        else:
            picked[field] = current
    return picked


def bounded(summary: dict) -> dict:
    text = json.dumps(summary, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) <= _MAX_SECTION_JSON:
        return summary
    return {"truncated": text[:_MAX_SECTION_JSON]}


def canonical(value: object) -> str:
    """A value read back from the diary went through JSON (tuples became lists)."""
    return json.dumps(value, sort_keys=True, default=str)


def needs_snapshot(last: dict | None, current: dict, keys: tuple[str, ...], *, now: float | None = None) -> bool:
    """Full once a day and on change, compared even across sessions, so a restart
    that changes nothing adds nothing."""
    if not last or not isinstance(last.get("t"), (int, float)):
        return True
    now = time.time() if now is None else now
    if time.strftime("%Y%m%d", time.localtime(last["t"])) != time.strftime("%Y%m%d", time.localtime(now)):
        return True
    return any(canonical(last.get(key)) != canonical(current.get(key)) for key in keys)


def section_changes(previous: dict | None, current: dict) -> dict:
    if previous is None:
        return dict(current)
    return {name: state for name, state in current.items() if previous.get(name) != state}


_TEMP_BANDS = (80, 90, 95)
_TEMP_HYSTERESIS = 3
_LOW_DRAW_RATIO = 0.5
_LOW_DRAW_MIN_W = 10
_TDP_STEP_W = 2
_LOW_DRAW_GPU_BUSY = 90


def _temp_band(temp: float | None, previous_band: int) -> int:
    if temp is None:
        return previous_band
    band = sum(1 for threshold in _TEMP_BANDS if temp >= threshold)
    if band < previous_band and temp > _TEMP_BANDS[previous_band - 1] - _TEMP_HYSTERESIS:
        return previous_band
    return band


class StateWatcher:
    """A sample becomes a line only when something moves: game, power source,
    control state, TDP by 2 W or more, a temperature band, a busy GPU drawing under
    half its TDP (an idle GPU drawing little is a light game, not a problem), or
    the heartbeat."""

    def __init__(self, heartbeat_s: float = 1800.0) -> None:
        self._heartbeat_s = heartbeat_s
        self._last: dict | None = None
        self._last_at: float | None = None
        self._band = 0
        self._low_draw_samples = 0
        self._low_draw = False

    def observe(self, sample: dict, now: float) -> str | None:
        temps = [value for value in (sample.get("cpu_c"), sample.get("gpu_c")) if isinstance(value, (int, float))]
        band = _temp_band(max(temps) if temps else None, self._band)
        low_draw = self._low_draw_state(sample)
        reason = self._reason(sample, band, low_draw, now)
        self._band = band
        self._low_draw = low_draw
        if reason is not None:
            self._last = dict(sample)
            self._last_at = now
        return reason

    def _low_draw_state(self, sample: dict) -> bool:
        watts, applied = sample.get("w"), sample.get("tdp_w")
        drawing_low = (
            sample.get("game") is not None
            and isinstance(watts, (int, float))
            and isinstance(applied, (int, float))
            and applied >= _LOW_DRAW_MIN_W
            and watts < applied * _LOW_DRAW_RATIO
            and isinstance(sample.get("gpu_busy"), (int, float))
            and sample["gpu_busy"] >= _LOW_DRAW_GPU_BUSY
        )
        self._low_draw_samples = self._low_draw_samples + 1 if drawing_low else 0
        if self._low_draw:
            return drawing_low
        return self._low_draw_samples >= 2

    def _reason(self, sample: dict, band: int, low_draw: bool, now: float) -> str | None:
        last = self._last
        if last is None:
            return "start"
        for key, reason in (("game", "game"), ("ac", "power_source"), ("control", "control")):
            if sample.get(key) != last.get(key):
                return reason
        tdp, last_tdp = sample.get("tdp_w"), last.get("tdp_w")
        if isinstance(tdp, (int, float)) and isinstance(last_tdp, (int, float)):
            if abs(tdp - last_tdp) >= _TDP_STEP_W:
                return "tdp"
        elif tdp != last_tdp:
            return "tdp"
        if band != self._band:
            return "temperature"
        if low_draw != self._low_draw:
            return "low_draw" if low_draw else "draw_recovered"
        if self._last_at is not None and now - self._last_at >= self._heartbeat_s:
            return "heartbeat"
        return None
