from __future__ import annotations

import os
from typing import Literal, Optional

MediaKind = Literal["image", "video", "audio"]

_TYPES: dict[str, tuple[MediaKind, str]] = {
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"),
    ".webp": ("image", "image/webp"),
    ".avif": ("image", "image/avif"),
    ".gif": ("image", "image/gif"),
    ".mp4": ("video", "video/mp4"),
    ".m4v": ("video", "video/mp4"),
    ".webm": ("video", "video/webm"),
    ".mp3": ("audio", "audio/mpeg"),
    ".ogg": ("audio", "audio/ogg"),
    ".opus": ("audio", "audio/ogg"),
    ".flac": ("audio", "audio/flac"),
    ".m4a": ("audio", "audio/mp4"),
    ".aac": ("audio", "audio/aac"),
    ".wav": ("audio", "audio/wav"),
}

MIME_TO_EXTENSION = {mime: ext for ext, (_, mime) in reversed(list(_TYPES.items()))}


def media_kind(path: str) -> Optional[MediaKind]:
    entry = _TYPES.get(os.path.splitext(path)[1].lower())
    return entry[0] if entry else None


def mime_type(path: str) -> Optional[str]:
    entry = _TYPES.get(os.path.splitext(path)[1].lower())
    return entry[1] if entry else None
