"""Newest official release of each tracked tool, verified by the SHA-256 digest GitHub publishes for it.

A tracked asset resolves to the newest matching release; the catalog's pinned asset is the fallback when the
release list can't be read or carries no digest. The last good answer is kept, so an offline install or an
exhausted API quota still gets the newest version this device has already seen.
"""

import json
import re
import time
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path

from http_util import ssl_context
from json_store import atomic_json_save

from .catalog import Asset

API = "https://api.github.com/repos/{repo}/releases?per_page=10"
FRESH_S = 6 * 3600
RETRY_S = 10 * 60
# Luma ships every game in each release: ten releases already weigh ~3 MB.
LIMIT = 8 * 1024 * 1024
MAX_SIZE = 1024 * 1024 * 1024


@dataclass(frozen=True)
class Track:
    repo: str
    name: str
    prerelease: bool = False


# Only tools whose newest release keeps the layout Panel installs; user-chosen FSR versions stay pinned.
TRACKS: dict[str, Track] = {
    "optiscaler-0.9.4": Track("optiscaler/OptiScaler", r"Optiscaler_0\.9\.\d+[^/]*\.7z"),
    "optiscaler-10-nightly": Track("optiscaler/OptiScaler-nightly", r"OptiScaler_v10\.\d+\.\d+[^/]*\.7z", prerelease=True),
    "reframework-nightly": Track("praydog/REFramework-nightly", r"REFramework\.zip"),
    "optipatcher-0.42": Track("optiscaler/OptiPatcher", r"OptiPatcher_v\d+\.\d+\.asi"),
    "luma-ff7-800": Track("Filoppi/Luma-Framework", r"Luma-Final_Fantasy_VII_Remake\.zip"),
    "helixsr-3.2.0": Track("lonewolf0622/HelixSR", r"HelixSR-3\.\d+\.\d+\.zip"),
}


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "panel-de-control-upscalers",
                                                   "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=10, context=ssl_context()) as response:
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("release list too large")
    return data


def newest(releases, track: Track) -> dict | None:
    """The newest published asset matching the track, with its digest; None when nothing qualifies."""
    if not isinstance(releases, list):
        return None
    pattern = re.compile(track.name)
    owner = f"https://github.com/{track.repo}/releases/download/"
    found = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        if release.get("prerelease") and not track.prerelease:
            continue
        for asset in release.get("assets") or ():
            name, url = asset.get("name", ""), asset.get("browser_download_url", "")
            digest, size = asset.get("digest") or "", asset.get("size")
            if (pattern.fullmatch(name) and url.startswith(owner) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
                    and type(size) is int and 0 < size <= MAX_SIZE):
                found.append({"published": str(release.get("published_at") or asset.get("updated_at") or ""),
                              "tag": str(release.get("tag_name") or ""), "filename": name, "url": url,
                              "sha256": digest[7:], "size": size})
    return max(found, key=lambda item: item["published"]) if found else None


class Resolver:
    def __init__(self, state_dir, fetch=None, clock=time.time, logger=None):
        self.path = Path(state_dir) / "latest-releases.json"
        self.fetch = fetch or (lambda url: _fetch(url))
        self.clock = clock
        self.logger = logger
        self._memory: dict | None = None

    def _load(self) -> dict:
        if self._memory is None:
            try:
                data = json.loads(self.path.read_text())
                self._memory = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                self._memory = {}
        return self._memory

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json_save(str(self.path), self._load())
        except OSError:
            pass

    def tracked(self, asset: Asset) -> bool:
        return asset.id in TRACKS

    def resolve(self, asset: Asset) -> Asset:
        track = TRACKS.get(asset.id)
        if track is None:
            return asset
        known = self._load().setdefault(asset.id, {})
        candidate = known.get("release")
        checked = known.get("checked")
        failed = float(known.get("failed") or 0)
        if (checked is None or self.clock() - float(checked) >= FRESH_S) and self.clock() - failed >= RETRY_S:
            try:
                found = newest(json.loads(self.fetch(API.format(repo=track.repo))), track)
                known["checked"] = self.clock()
                if found:
                    candidate = known["release"] = found
                self._save()
            except Exception as error:  # noqa: BLE001 — any failure keeps the last good answer
                known["failed"] = self.clock()
                if self.logger:
                    self.logger.info(f"Latest {asset.id} unavailable ({type(error).__name__}); using the last known")
        if not candidate or candidate.get("sha256") == asset.sha256:
            return asset
        return replace(asset, filename=candidate["filename"], sha256=candidate["sha256"], size=candidate["size"],
                       urls=(candidate["url"],))

    def version(self, asset: Asset) -> str | None:
        release = self._load().get(asset.id, {}).get("release") or {}
        return release.get("tag") if release.get("sha256") == asset.sha256 else None
