from __future__ import annotations

import errno
import hashlib
import os
import threading
import time
from typing import Callable, Optional

from ..core.image_header import ImageInfo
from .optimizer import OptimizeError, _run, find_ffmpeg

BUCKETS = (1280, 1920, 2560)
MAX_PIXELS = 100_000_000
SCALE_TIMEOUT_SEC = 20
CACHE_MAX_FILES = 96
CACHE_MAX_BYTES = 256 * 1024 * 1024
# A copy served in the last minute is never pruned, so a request that found it is not answered with a 404.
PRUNE_GRACE_SEC = 60
JPEG_QSCALE = "3"  # ffmpeg's mjpeg scale (2 best .. 31 worst); 3 looks like quality ~85

# ffmpeg's transpose: 0 = rotate counter-clockwise and flip vertically (EXIF "transpose"), 1 = clockwise,
# 2 = counter-clockwise, 3 = clockwise and flip vertically (EXIF "transverse").
_ORIENTATION_FILTERS = {
    2: ["hflip"],
    3: ["hflip", "vflip"],
    4: ["vflip"],
    5: ["transpose=0"],
    6: ["transpose=1"],
    7: ["transpose=3"],
    8: ["transpose=2"],
}

Runner = Callable[[list[str], Optional[threading.Event], float], int]


def bucket_for(max_side: object) -> int:
    """The smallest size that covers the screen; anything unknown or bigger gets the 1440p cap."""
    if isinstance(max_side, bool) or not isinstance(max_side, (int, float)) or not max_side > 0:
        return BUCKETS[-1]
    return next((bucket for bucket in BUCKETS if max_side <= bucket), BUCKETS[-1])


def servable(info: Optional[ImageInfo]) -> bool:
    return info is not None and info.pixels <= MAX_PIXELS


def needs_copy(info: ImageInfo, bucket: int) -> bool:
    return info.long_side > bucket


def _ref_prefix(ref: str) -> str:
    return "img-" + hashlib.sha256(ref.encode("utf-8")).hexdigest()[:16] + "-"


def output_name(ref: str, source: str, info: ImageInfo, bucket: int) -> Optional[str]:
    """Prefixed by the ref so forgetting a picture finds every copy, whichever version of the file made it.
    None when the source is gone."""
    try:
        stat = os.stat(source)
    except OSError:
        return None
    key = f"{os.path.realpath(source)}:{stat.st_size}:{stat.st_mtime_ns}:{bucket}"
    return _ref_prefix(ref) + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24] + (".png" if info.alpha else ".jpg")


def scale_command(ffmpeg: str, source: str, target: str, info: ImageInfo, bucket: int) -> list[str]:
    # -noautorotate: the EXIF orientation is applied once, here, whatever this ffmpeg build does on its own.
    filters = [*_ORIENTATION_FILTERS.get(info.orientation, []), f"scale=w={bucket}:h={bucket}:force_original_aspect_ratio=decrease:flags=lanczos"]
    encode = ["-c:v", "png"] if info.alpha else ["-c:v", "mjpeg", "-q:v", JPEG_QSCALE, "-pix_fmt", "yuvj420p"]
    return [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-noautorotate", "-i", source,
        "-vf", ",".join(filters), "-frames:v", "1", "-map_metadata", "-1", *encode, "-f", "image2", target,
    ]


class ImageScaler:
    """Screen-sized copies of theme pictures, made once per source version and size, one at a time."""

    def __init__(self, cache_dir: str, find: Callable[[], Optional[str]] = find_ffmpeg, run: Runner = _run):
        self._cache_dir = cache_dir
        self._find = find
        self._run = run
        self._lock = threading.Lock()

    def scaled(self, ref: str, source: str, info: ImageInfo, bucket: int) -> Optional[str]:
        """Path of the copy, made on first use; None when the source is gone. Raises OptimizeError when the
        copy cannot be made.

        A copy that exists is served without the lock, so it never waits behind another picture's encode;
        the lock only serializes encodes, and the re-check inside it makes one encode per missing copy.
        Touching the copy is what claims it: a copy pruned before the touch is simply made again."""
        if not servable(info):
            raise OptimizeError("too_large")
        name = output_name(ref, source, info, bucket)
        if name is None:
            return None
        target = os.path.join(self._cache_dir, name)
        if _touch(target):
            return target
        with self._lock:
            if _touch(target):
                return target
            ffmpeg = self._find()
            if ffmpeg is None:
                raise OptimizeError("no_encoder")
            partial = target[:-4] + ".part" + target[-4:]
            try:
                os.makedirs(self._cache_dir, exist_ok=True)
                code = self._run(scale_command(ffmpeg, source, partial, info, bucket), None, SCALE_TIMEOUT_SEC)
                if code != 0 or not os.path.isfile(partial) or os.path.getsize(partial) == 0:
                    raise OptimizeError("encode_failed")
                os.replace(partial, target)
            except OSError as error:
                raise OptimizeError("no_space" if error.errno in (errno.ENOSPC, errno.EDQUOT) else "encode_failed") from error
            finally:
                if os.path.exists(partial):
                    os.unlink(partial)
            self._prune(keep=target)
            return target

    def forget(self, ref: str) -> int:
        """Deletes every copy of one picture (never the original); returns how many were removed."""
        prefix = _ref_prefix(ref)
        removed = 0
        with self._lock:
            try:
                entries = [entry for entry in os.scandir(self._cache_dir) if entry.name.startswith(prefix)]
            except OSError:
                return 0
            for entry in entries:
                try:
                    os.unlink(entry.path)
                    removed += 1
                except OSError:
                    continue
        return removed

    def _prune(self, keep: str) -> None:
        try:
            entries = [(entry.path, entry.stat()) for entry in os.scandir(self._cache_dir) if entry.is_file() and ".part." not in entry.name]
        except OSError:
            return
        entries.sort(key=lambda item: item[1].st_mtime)
        total = sum(stat.st_size for _, stat in entries)
        count = len(entries)
        for path, stat in entries:
            if count <= CACHE_MAX_FILES and total <= CACHE_MAX_BYTES:
                break
            if path == keep:
                continue
            # Re-read: a request may have touched it since the listing, and then it is being served.
            try:
                if time.time() - os.stat(path).st_mtime < PRUNE_GRACE_SEC:
                    continue
                os.unlink(path)
            except OSError:
                continue
            count -= 1
            total -= stat.st_size


def _touch(path: str) -> bool:
    """Marks a copy as just used; False when it does not exist (never made, or pruned meanwhile)."""
    try:
        os.utime(path)
    except OSError:
        return False
    return os.path.isfile(path)
