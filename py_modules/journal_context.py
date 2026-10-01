"""What surrounds Panel on this machine, written to the diary only when it changes.

Support questions are mostly "who else was touching power or fans, and what was the
machine doing when it went wrong". The diary answers them with two kinds of line:
the context (Decky plugins and power/fan services, flagging the ones that compete
with Panel) and a state snapshot taken when something meaningful moves, never on a
clock alone, so a week of play stays short enough to read.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable

# Normalised Decky plugin name -> what it competes with Panel for.
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
# Service unit stem -> what it can write.
_POWER_SERVICES = {
    "hhd": "tdp",
    "powerstation": "tdp",
    "power-profiles-daemon": "profile",
    "tuned": "profile",
    "tuned-ppd": "profile",
    "steamos-manager": "tdp",
    "jupiter-fan-control": "fans",
    "fw-fanctrl": "fans",
    "inputplumber": "controller",
    "handycon": "controller",
}
_UNIT = re.compile(r"^(?P<stem>[A-Za-z0-9_.-]+?)(?:@[^.\s]*)?\.service$")
_MAX_PLUGINS = 64


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def plugin_inventory(plugins_dir: str, loader_settings: str) -> list[dict]:
    """Every installed Decky plugin with its version and whether Decky has it on."""
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
    """Running services that can write power, fan or controller state."""
    output = run(["systemctl", "list-units", "--type=service", "--state=active", "--no-legend", "--plain"])
    found = set()
    for line in (output or "").splitlines():
        unit = line.split(None, 1)[0] if line.strip() else ""
        match = _UNIT.match(unit)
        if match and match.group("stem") in _POWER_SERVICES:
            found.add(match.group("stem"))
    return sorted(found)


def rivals(plugins: list[dict], services: list[str]) -> list[dict]:
    """The plugins and services that write what Panel writes."""
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
    """What changed since the last context line, or None when nothing did."""
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


_MAX_SECTION_JSON = 2000


def pick_fields(value: object, fields: tuple[str, ...] | None) -> object:
    """The named fields of a section getter's result (dotted paths reach into
    nested dicts); None keeps the whole value. Missing fields are left out."""
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
    """A section summary short enough for one diary line."""
    text = json.dumps(summary, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) <= _MAX_SECTION_JSON:
        return summary
    return {"truncated": text[:_MAX_SECTION_JSON]}


def section_changes(previous: dict | None, current: dict) -> dict:
    """The sections whose applied state differs from the last line, in full."""
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
    """Decides which samples become a diary line: the first one, then only when
    the game, the power source or Panel's control state change, the applied TDP
    moves 2 W or more, the hottest sensor crosses 80/90/95 °C, a game keeps the GPU
    busy yet draws under half its TDP for two samples in a row (or stops doing so),
    or nothing was written for the heartbeat. A light game drawing little with an
    idle GPU is not a low draw."""

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
