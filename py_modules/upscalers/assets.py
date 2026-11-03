"""Download, verify and unpack catalog assets into the plugin's cache."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from http_util import ssl_context

from .catalog import Asset

CHUNK = 256 * 1024
TIMEOUT_S = 30
RETRIES = 3
BACKOFF_S = (2, 5)
USER_AGENT = "panel-de-control-upscalers"

Progress = Callable[[int], None]


def _wait(seconds: float, cancelled: Callable[[], bool]) -> bool:
    """Sleep in short steps; False as soon as the user cancels."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cancelled():
            return False
        time.sleep(0.1)
    return not cancelled()


class AssetError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AssetCache:
    def __init__(self, root: Path):
        self.root = root

    def file(self, asset: Asset) -> Path:
        return self.root / asset.sha256 / asset.filename

    def unpacked(self, asset: Asset) -> Path:
        return self.root / asset.sha256 / "unpacked"

    def member(self, asset: Asset) -> Path:
        return self.unpacked(asset) / str(asset.member)

    def ready(self, asset: Asset) -> bool:
        if asset.archive:
            return (self.unpacked(asset) / ".complete").is_file()
        if asset.member:
            return self.member(asset).is_file()
        return self.file(asset).is_file()

    def ensure(self, asset: Asset, progress: Progress, cancelled: Callable[[], bool]) -> Path:
        """Return the verified file (or unpacked folder for archives), fetching it if needed."""
        if not self.ready(asset):
            self._download(asset, progress, cancelled)
            if asset.archive:
                self._unpack(asset)
            elif asset.member:
                self._extract_member(asset)
        else:
            progress(asset.size)
        if asset.archive:
            return self.unpacked(asset)
        return self.member(asset) if asset.member else self.file(asset)

    def _extract_member(self, asset: Asset) -> None:
        """Copy one named file out of a verified zip, never anything else it carries."""
        target = self.member(asset)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(self.file(asset)) as archive:
                info = archive.getinfo(str(asset.member))
                fd, partial = tempfile.mkstemp(dir=target.parent, prefix=".part-")
                with os.fdopen(fd, "wb") as out, archive.open(info) as source:
                    shutil.copyfileobj(source, out)
                os.replace(partial, target)
        except (KeyError, zipfile.BadZipFile, OSError) as error:
            raise AssetError("unpack_failed", type(error).__name__) from None

    def partial(self, asset: Asset) -> Path:
        """Kept across attempts and restarts so a dropped download resumes instead of starting over."""
        return self.file(asset).with_name(f".part-{asset.filename}")

    def _download(self, asset: Asset, progress: Progress, cancelled: Callable[[], bool]) -> None:
        target = self.file(asset)
        if target.is_file() and target.stat().st_size == asset.size and sha256(target) == asset.sha256:
            progress(asset.size)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        self._check_space(asset)
        last_error = AssetError("download_failed")
        for url in asset.urls:
            for attempt in range(RETRIES):
                if attempt and not _wait(BACKOFF_S[min(attempt - 1, len(BACKOFF_S) - 1)], cancelled):
                    raise AssetError("cancelled")
                try:
                    self._fetch(url, asset, progress, cancelled)
                    os.replace(self.partial(asset), target)
                    return
                except AssetError as error:
                    last_error = error
                    if error.code in ("cancelled", "no_space"):
                        raise
                    self.partial(asset).unlink(missing_ok=True)
                    break
                except OSError as error:
                    last_error = AssetError("download_failed", f"{type(error).__name__}: {error}"[:200])
        raise last_error

    def _check_space(self, asset: Asset) -> None:
        have = self.partial(asset).stat().st_size if self.partial(asset).is_file() else 0
        # Archives are unpacked next to the download, so they need room for both.
        need = asset.size - have + (asset.size * 2 if asset.archive else 0)
        free = shutil.disk_usage(self.root if self.root.exists() else self.root.parent).free
        if free < need:
            raise AssetError("no_space", str(need - free))

    def _fetch(self, url: str, asset: Asset, progress: Progress, cancelled: Callable[[], bool]) -> None:
        partial = self.partial(asset)
        have = partial.stat().st_size if partial.is_file() else 0
        if have >= asset.size:
            partial.unlink()
            have = 0
        headers = {"User-Agent": USER_AGENT}
        if have:
            headers["Range"] = f"bytes={have}-"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=TIMEOUT_S, context=ssl_context()) as response:
            if have and getattr(response, "status", 200) != 206:
                have = 0
            digest = hashlib.sha256()
            if have:
                with open(partial, "rb") as existing:
                    for chunk in iter(lambda: existing.read(CHUNK), b""):
                        digest.update(chunk)
            received = have
            progress(received)
            with open(partial, "ab" if have else "wb") as out:
                while True:
                    if cancelled():
                        raise AssetError("cancelled")
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > asset.size:
                        raise AssetError("size_mismatch")
                    digest.update(chunk)
                    out.write(chunk)
                    progress(received)
        if received != asset.size:
            raise OSError(f"stopped at {received} of {asset.size} bytes")
        if digest.hexdigest() != asset.sha256:
            raise AssetError("hash_mismatch")

    def _unpack(self, asset: Asset) -> None:
        destination = self.unpacked(asset)
        shutil.rmtree(destination, ignore_errors=True)
        staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=".unpack-"))
        try:
            for tool in (["bsdtar", "-xf"], ["7z", "x", "-y", f"-o{staging}"]):
                if shutil.which(tool[0]) is None:
                    continue
                command = [*tool, str(self.file(asset))]
                if tool[0] == "bsdtar":
                    command += ["-C", str(staging)]
                result = subprocess.run(command, capture_output=True, timeout=300, check=False)
                if result.returncode == 0:
                    break
            else:
                raise AssetError("unpack_failed")
            for path in staging.rglob("*"):
                if path.is_symlink() or not path.resolve().is_relative_to(staging.resolve()):
                    raise AssetError("unsafe_archive")
            (staging / ".complete").write_text(asset.sha256)
            os.replace(staging, destination)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
