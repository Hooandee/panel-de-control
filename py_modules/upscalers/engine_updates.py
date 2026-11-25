"""Official stable motor discovery and bounded downloads."""

import hashlib
import json
import os
import re
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

from http_util import ssl_context
from .catalog import Asset

MAKO_RELEASES = "https://api.github.com/repos/eugeniosegala/MAKO/releases?per_page=30"
LSFG_BUILDS = "https://builds.lsfg-vk.dev/"
MAX_ARCHIVE = 64 * 1024 * 1024


class UpdateError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def version(value):
    match = re.fullmatch(r"(?:lsfg-vk-)?(\d+)\.(\d+)\.(\d+)", str(value))
    if not match:
        raise UpdateError("engine_version")
    return tuple(map(int, match.groups()))


def fetch(url, limit):
    request = urllib.request.Request(url, headers={"User-Agent": "panel-de-control-upscalers"})
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=10, context=ssl_context()) as response:
        data = bytearray()
        while chunk := response.read(min(65536, limit + 1 - len(data))):
            data.extend(chunk)
            if len(data) > limit or time.monotonic() - started > 45:
                raise UpdateError("engine_download_limit")
        return bytes(data)


def discover(engine, current):
    baseline = version(current)
    candidates = []
    if engine == "mako":
        releases = json.loads(fetch(MAKO_RELEASES, 2 * 1024 * 1024))
        if not isinstance(releases, list):
            raise UpdateError("engine_metadata")
        for release in releases:
            if release.get("draft") or release.get("prerelease"):
                continue
            match = re.fullmatch(r"render-v(\d+\.\d+\.\d+)", release.get("tag_name", ""))
            if not match:
                continue
            number = match[1]
            filename = f"MAKO-Renderer-v{number}-linux.tar.xz"
            url = f"https://github.com/eugeniosegala/MAKO/releases/download/render-v{number}/{filename}"
            for asset in release.get("assets", []):
                digest = asset.get("digest") or ""
                size = asset.get("size", 0)
                if (asset.get("name") == filename and asset.get("browser_download_url") == url
                        and re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
                        and type(size) is int and 0 < size <= MAX_ARCHIVE):
                    candidates.append({"version": number, "url": url, "sha256": digest[7:], "size": size})
    elif engine == "lsfg":
        page = fetch(LSFG_BUILDS, 256 * 1024).decode("utf-8")
        for number in set(re.findall(r'href="lsfg-vk-(\d+\.\d+\.\d+)\.tar\.xz"', page)):
            candidates.append({"version": number, "url": LSFG_BUILDS + f"lsfg-vk-{number}.tar.xz"})
    else:
        raise UpdateError("engine_unknown")
    compatible = [c for c in candidates if version(c["version"])[0] == baseline[0] and version(c["version"]) > baseline]
    return max(compatible, key=lambda c: version(c["version"])) if compatible else None


def prepare(engine, candidate, cache):
    content = fetch(candidate["url"], MAX_ARCHIVE)
    digest = hashlib.sha256(content).hexdigest()
    if candidate.get("sha256") and digest != candidate["sha256"]:
        raise UpdateError("engine_checksum")
    if candidate.get("size") and len(content) != candidate["size"]:
        raise UpdateError("engine_checksum")
    number = candidate["version"]
    asset = Asset(f"{engine}-{number}", candidate["url"].rsplit("/", 1)[1], digest, len(content), (candidate["url"],))
    path = cache.file(asset)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return asset


def unpack_lsfg(path, destination, names):
    found = set()
    with tarfile.open(path, "r:xz") as archive:
        for member in archive:
            name = str(Path(member.name))
            if Path(name).is_absolute() or ".." in Path(name).parts or member.issym() or member.islnk():
                raise UpdateError("engine_archive")
            if name not in names:
                continue
            if name in found or not member.isfile() or not 0 < member.size <= 32 * 1024 * 1024:
                raise UpdateError("engine_archive")
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
            found.add(name)
    if found != set(names):
        raise UpdateError("engine_archive")
