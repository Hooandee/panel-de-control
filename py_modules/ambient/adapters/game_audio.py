from __future__ import annotations

import json
import subprocess
from typing import Any, Callable, Optional

from pdc_platform.user_session import find_session, session_command

# Steam's own UI plays Ambiente's media, so its streams are never the game's.
_STEAM_BINARIES = frozenset({"steamwebhelper", "steam"})
_TIMEOUT_S = 3

Runner = Callable[[list[str]], Optional[str]]


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
        channels = [c for c in (stream.get("volume") or {}).values() if isinstance(c, dict)]
        percents = [int(str(c.get("value_percent", "100")).rstrip("%") or 100) for c in channels]
        streams.append((index, max(percents) if percents else 100))
    return streams


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
