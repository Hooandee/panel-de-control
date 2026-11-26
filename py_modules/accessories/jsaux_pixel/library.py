"""The user's own drawings and imported art, kept on the Steam Machine (not on the panel)."""

import base64
import json
import re
import time
import uuid
from pathlib import Path

from json_store import atomic_json_save

FRAME_BYTES = 64 * 54 * 3
MAX_FRAMES = 48
_ID = re.compile(r"^[a-f0-9]{12}$")


def _valid_id(drawing_id: str) -> str:
    if not isinstance(drawing_id, str) or not _ID.match(drawing_id):
        raise ValueError("invalid drawing id")
    return drawing_id


class Library:
    def __init__(self, root: Path):
        self._root = Path(root)

    def _path(self, drawing_id: str) -> Path:
        return self._root / f"{_valid_id(drawing_id)}.json"

    def save(self, drawing: dict) -> dict:
        frames = drawing.get("frames")
        if not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES:
            raise ValueError("a drawing needs between 1 and 48 frames")
        for frame in frames:
            try:
                raw = base64.b64decode(str(frame), validate=True)
            except ValueError as error:
                raise ValueError("frame is not base64") from error
            if len(raw) != FRAME_BYTES:
                raise ValueError("frame size does not match the panel")
        fps = drawing.get("fps")
        if not isinstance(fps, int) or not 1 <= fps <= 30:
            raise ValueError("fps must be between 1 and 30")
        drawing_id = _valid_id(drawing["id"]) if drawing.get("id") else uuid.uuid4().hex[:12]
        record = {"id": drawing_id, "name": str(drawing.get("name") or "")[:40], "frames": frames,
                  "fps": fps, "updated": time.time()}
        self._root.mkdir(parents=True, exist_ok=True)
        atomic_json_save(str(self._path(drawing_id)), record)
        return {"id": drawing_id, "name": record["name"]}

    def load(self, drawing_id: str) -> dict | None:
        path = self._path(drawing_id)
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def delete(self, drawing_id: str) -> None:
        try:
            self._path(drawing_id).unlink()
        except FileNotFoundError:
            pass

    def list(self) -> list[dict]:
        items = []
        for path in sorted(self._root.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                items.append({"id": data["id"], "name": data.get("name", ""), "frames": len(data["frames"]),
                              "fps": data.get("fps", 8), "thumb": data["frames"][0], "updated": data.get("updated", 0)})
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                continue
        return sorted(items, key=lambda item: -item["updated"])
