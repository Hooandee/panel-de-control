from __future__ import annotations

import json
import subprocess
from typing import Any, Callable, Optional

from pdc_platform.user_session import find_session, session_command

# Steam's own UI plays Ambiente's media, so its streams are never the game's.
_STEAM_BINARIES = frozenset({"steamwebhelper", "steam"})
_TIMEOUT_S = 3


Runner = Callable[[list[str]], Optional[str]]


def _sink_kind(name: str) -> str:
    """Bus and profile of a sink without the middle, which holds Bluetooth addresses and USB serials."""
    parts = name.split(".")
    return f"{parts[0]}..{parts[-1]}" if len(parts) > 2 else parts[0][:60]


def _volume_percents(stream: dict[str, Any]) -> list[int]:
    channels = [c for c in (stream.get("volume") or {}).values() if isinstance(c, dict)]
    return [int(p) for p in (str(c.get("value_percent", "")).rstrip("%") for c in channels) if p.isdigit()]


def game_streams(sink_inputs: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Pulse sink inputs that belong to a game, as (index, current volume percent)."""
    streams: list[tuple[int, int]] = []
    for stream in sink_inputs:
        props = stream.get("properties") or {}
        if props.get("application.process.binary") in _STEAM_BINARIES:
            continue
        if str(props.get("node.name", "")).startswith("effect_"):
            continue
        index = stream.get("index")
        if not isinstance(index, int):
            continue
        streams.append((index, max(_volume_percents(stream), default=100)))
    return streams


def steam_streams(sink_inputs: list[dict[str, Any]]) -> list[str]:
    """Steam's own sink inputs (where Ambiente sounds): volume, mute, paused and the sink they go to."""
    found: list[str] = []
    for stream in sink_inputs:
        props = stream.get("properties") or {}
        if props.get("application.process.binary") not in _STEAM_BINARIES:
            continue
        found.append(f"vol={max(_volume_percents(stream), default='?')} mute={stream.get('mute')} corked={stream.get('corked')} sink={stream.get('sink')}")
    return found


class GameAudio:
    """Sets the volume of the running game's audio streams, leaving Steam's own audio alone."""

    def __init__(self, runner: Optional[Runner] = None):
        self._runner = runner or self._run

    def _run(self, argv: list[str]) -> Optional[str]:
        cmd, env, identity = session_command(find_session(), argv)
        if cmd is None:
            return None
        try:
            out = subprocess.run(cmd, env=env, check=False, capture_output=True, timeout=_TIMEOUT_S, text=True, **identity)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout if out.returncode == 0 else None

    def steam_output(self) -> str:
        listing = self._runner(["pactl", "-f", "json", "list", "sink-inputs"])
        try:
            parsed = json.loads(listing) if listing is not None else None
        except ValueError:
            parsed = None
        if not isinstance(parsed, list):
            return "unreadable"
        streams = steam_streams(parsed)
        default = _sink_kind((self._runner(["pactl", "get-default-sink"]) or "?").strip())
        return f"streams={len(streams)} default_sink={default[:60]} " + " | ".join(streams[:4])

    def set_level(self, percent: int) -> dict[str, Any]:
        percent = int(max(0, min(100, percent)))
        listing = self._runner(["pactl", "-f", "json", "list", "sink-inputs"])
        if listing is None:
            return {"supported": False, "streams": 0}
        try:
            parsed = json.loads(listing)
        except ValueError:
            return {"supported": False, "streams": 0}
        streams = game_streams(parsed if isinstance(parsed, list) else [])
        for index, current in streams:
            if current != percent:
                self._runner(["pactl", "set-sink-input-volume", str(index), f"{percent}%"])
        return {"supported": True, "streams": len(streams)}
