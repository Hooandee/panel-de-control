"""Download, verify and unpack catalog assets into the plugin's cache."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

from http_util import ssl_context

from .catalog import Asset

CHUNK = 256 * 1024
TIMEOUT_S = 30
USER_AGENT = "panel-de-control-upscalers"

Progress = Callable[[int], None]


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

    def ready(self, asset: Asset) -> bool:
        if asset.archive:
            return (self.unpacked(asset) / ".complete").is_file()
        return self.file(asset).is_file()

    def ensure(self, asset: Asset, progress: Progress, cancelled: Callable[[], bool]) -> Path:
        """Return the verified file (or unpacked folder for archives), fetching it if needed."""
        if not self.ready(asset):
            self._download(asset, progress, cancelled)
            if asset.archive:
                self._unpack(asset)
        else:
            progress(asset.size)
        return self.unpacked(asset) if asset.archive else self.file(asset)

    def _download(self, asset: Asset, progress: Progress, cancelled: Callable[[], bool]) -> None:
        target = self.file(asset)
        if target.is_file() and target.stat().st_size == asset.size and sha256(target) == asset.sha256:
            progress(asset.size)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        last_error = AssetError("download_failed")
        for url in asset.urls:
            fd, partial = tempfile.mkstemp(dir=target.parent, prefix=".part-")
            digest = hashlib.sha256()
            received = 0
            try:
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with os.fdopen(fd, "wb") as out, urllib.request.urlopen(request, timeout=TIMEOUT_S, context=ssl_context()) as response:
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
                if received != asset.size or digest.hexdigest() != asset.sha256:
                    raise AssetError("hash_mismatch")
                os.replace(partial, target)
                return
            except AssetError as error:
                last_error = error
                if error.code == "cancelled":
                    raise
            except OSError as error:
                last_error = AssetError("download_failed", f"{type(error).__name__}: {error}"[:200])
            finally:
                if os.path.exists(partial):
                    os.unlink(partial)
            progress(0)
        raise last_error

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
