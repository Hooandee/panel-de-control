from __future__ import annotations

import hashlib
from typing import Optional

from .media_types import MIME_TO_EXTENSION

DAILY_TTL_SEC = 24 * 3600


def cache_filename(url: str, mime: str) -> Optional[str]:
    extension = MIME_TO_EXTENSION.get(mime.split(";")[0].strip().lower())
    if extension is None:
        return None
    return hashlib.sha256(url.encode("utf-8")).hexdigest() + extension


def is_expired(fetched_at: float, now: float, daily: bool) -> bool:
    return daily and now - fetched_at >= DAILY_TTL_SEC
