from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from theme_remote import ThemeRuntimeVersions


_STABLE_SEMVER = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
_PANEL_RUNTIME_SEMVER = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?$"
)
_BACKEND_VERSION = re.compile(
    r"^CSS_LOADER_VER\s*=\s*([1-9][0-9]*)\s*$",
    re.MULTILINE,
)
_MAX_RUNTIME_FILE_BYTES = 64 * 1024
_MAX_SAFE_INTEGER_TEXT = "9007199254740991"


class ThemeRuntimeProbeError(Exception):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ThemeRuntimeProbeError("CSS Loader package metadata is invalid")
        value[key] = child
    return value


def _read_regular_file(directory: int, name: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, dir_fd=directory)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_RUNTIME_FILE_BYTES:
            raise ThemeRuntimeProbeError("CSS Loader runtime file is invalid")
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(descriptor, min(8192, _MAX_RUNTIME_FILE_BYTES - total + 1))
            if not block:
                break
            total += len(block)
            if total > _MAX_RUNTIME_FILE_BYTES:
                raise ThemeRuntimeProbeError("CSS Loader runtime file is invalid")
            chunks.append(block)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def probe_css_loader_runtime(
    plugins_root: str | Path,
    *,
    panel_version: str,
) -> ThemeRuntimeVersions:
    if _PANEL_RUNTIME_SEMVER.fullmatch(panel_version) is None:
        raise ThemeRuntimeProbeError("Panel runtime version is invalid")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    plugins_descriptor = -1
    css_loader_descriptor = -1
    try:
        plugins_descriptor = os.open(os.fspath(plugins_root), directory_flags)
        css_loader_descriptor = os.open(
            "SDH-CssLoader",
            directory_flags,
            dir_fd=plugins_descriptor,
        )
        package_bytes = _read_regular_file(css_loader_descriptor, "package.json")
        backend_bytes = _read_regular_file(css_loader_descriptor, "css_theme.py")
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ThemeRuntimeProbeError("CSS Loader runtime is unavailable") from error
    finally:
        if css_loader_descriptor >= 0:
            os.close(css_loader_descriptor)
        if plugins_descriptor >= 0:
            os.close(plugins_descriptor)

    try:
        package = json.loads(
            package_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
        )
        backend_source = backend_bytes.decode("utf-8", errors="strict")
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ThemeRuntimeProbeError("CSS Loader runtime metadata is invalid") from error
    if not isinstance(package, dict) or package.get("name") != "SDH-CssLoader":
        raise ThemeRuntimeProbeError("CSS Loader package identity is invalid")
    css_loader_version = package.get("version")
    if not isinstance(css_loader_version, str) or _STABLE_SEMVER.fullmatch(
        css_loader_version
    ) is None:
        raise ThemeRuntimeProbeError("CSS Loader package version is invalid")
    backend_matches = _BACKEND_VERSION.findall(backend_source)
    if len(backend_matches) != 1:
        raise ThemeRuntimeProbeError("CSS Loader backend version is invalid")
    backend_text = backend_matches[0]
    if len(backend_text) > len(_MAX_SAFE_INTEGER_TEXT) or (
        len(backend_text) == len(_MAX_SAFE_INTEGER_TEXT)
        and backend_text > _MAX_SAFE_INTEGER_TEXT
    ):
        raise ThemeRuntimeProbeError("CSS Loader backend version is invalid")
    backend_version = int(backend_text)
    return ThemeRuntimeVersions(
        panel=panel_version,
        css_loader=css_loader_version,
        css_loader_backend=backend_version,
    )
