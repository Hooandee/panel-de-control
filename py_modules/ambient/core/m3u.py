from __future__ import annotations

import hashlib
import re
from typing import Any

MAX_CHANNELS = 10000
_ATTRIBUTE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')


def _clean(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


def parse_m3u(text: str) -> list[dict[str, Any]]:
    """Channels of an extended M3U playlist: name, stream URL, logo and group.

    Only http(s) streams are kept; everything else in the file is ignored.
    """
    channels: list[dict[str, Any]] = []
    seen: set[str] = set()
    pending: dict[str, str] = {}
    group = ""
    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿")
        if not line:
            continue
        if line.upper().startswith("#EXTINF"):
            header, _, title = line.partition(",")
            attributes = dict(_ATTRIBUTE.findall(header))
            pending = {
                "name": _clean(title or attributes.get("tvg-name", ""), 120),
                "logo": attributes.get("tvg-logo", ""),
                "group": _clean(attributes.get("group-title", ""), 80),
            }
            continue
        if line.upper().startswith("#EXTGRP:"):
            group = _clean(line.split(":", 1)[1], 80)
            continue
        if line.startswith("#"):
            continue
        if not line.lower().startswith(("http://", "https://")) or len(line) > 2048 or line in seen:
            pending = {}
            continue
        seen.add(line)
        logo = pending.get("logo", "")
        channels.append({
            "id": "ch." + hashlib.sha1(line.encode("utf-8")).hexdigest()[:12],
            "name": pending.get("name") or line.rsplit("/", 1)[-1][:120] or line[:120],
            "url": line,
            "logo": logo if logo.lower().startswith("https://") and len(logo) <= 2048 else "",
            "group": pending.get("group") or group,
        })
        pending = {}
        if len(channels) >= MAX_CHANNELS:
            break
    return channels


def is_channel_list(text: str) -> bool:
    """An IPTV/radio list (several channels, each its own stream), not an HLS playlist or a station's mirrors.

    HLS media and master playlists always carry #EXT-X- tags; channel lists such as TDTChannels'
    `tv.m3u8` share the extension but never do.
    """
    if "#EXT-X-" in text.upper():
        return False
    channels = parse_m3u(text)
    # A station's own .m3u often lists a few mirrors of one stream; a channel list names or groups its entries.
    named = len({c["name"] for c in channels}) >= 2 and ("group-title=" in text or "tvg-" in text)
    return len(channels) >= 2 and (named or len(channels) >= 10)
