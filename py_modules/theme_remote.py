from __future__ import annotations

import re
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import theme_packages
from theme_remote_contract import ThemeContractError, ThemeRelease, parse_theme_release
from theme_transport import ThemeTransportError


_RUNTIME_SEMVER = re.compile(
    r"^(?:v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?$"
)
_CACHE_SECONDS = 15 * 60


@dataclass(frozen=True)
class OfficialThemeRegistration:
    catalog_id: str
    css_loader_name: str
    latest_path: str


@dataclass(frozen=True)
class OfficialThemeChannel:
    pages_base_url: str
    themes: tuple[OfficialThemeRegistration, ...]


@dataclass(frozen=True)
class ThemeRuntimeVersions:
    panel: str
    css_loader: str
    css_loader_backend: int


class ThemeMetadataTransport(Protocol):
    def fetch_metadata(self, relative_path: str) -> bytes: ...

    def download_artifact(
        self,
        relative_path: str,
        destination: str | Path,
        *,
        expected_size: int,
        expected_sha256: str,
    ) -> object: ...


@dataclass(frozen=True)
class _CachedRelease:
    release: ThemeRelease
    checked_at: float


class ThemeRemoteError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _parse_runtime_version(value: str) -> tuple[int, int, int, tuple[str, ...]] | None:
    if not isinstance(value, str):
        return None
    match = _RUNTIME_SEMVER.fullmatch(value)
    if match is None:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        tuple(match.group(4).split(".")) if match.group(4) else (),
    )


def _runtime_meets(value: str, minimum: str) -> bool:
    running = _parse_runtime_version(value)
    required = _parse_runtime_version(minimum)
    if running is None or required is None:
        return False
    if running[:3] != required[:3]:
        return running[:3] > required[:3]
    if not required[3]:
        return not running[3]
    if not running[3]:
        return True
    return running[3] >= required[3]


def _compatibility(
    release: ThemeRelease,
    runtime: ThemeRuntimeVersions,
) -> str:
    minimum = release.minimum_versions
    if not _runtime_meets(runtime.panel, minimum.panel):
        return "incompatible-panel"
    if (
        not _runtime_meets(runtime.css_loader, minimum.css_loader)
        or not isinstance(runtime.css_loader_backend, int)
        or isinstance(runtime.css_loader_backend, bool)
        or runtime.css_loader_backend < minimum.css_loader_backend
    ):
        return "incompatible-css-loader"
    return "compatible"


def _theme_dto(release: ThemeRelease, runtime: ThemeRuntimeVersions) -> dict[str, object]:
    return {
        "catalogId": release.catalog_id,
        "cssLoaderName": release.css_loader_name,
        "publishedVersion": release.version,
        "compatibility": _compatibility(release, runtime),
        "notes": dict(release.notes),
    }


class ThemeRemoteService:
    def __init__(
        self,
        channel: OfficialThemeChannel | None,
        *,
        transport: ThemeMetadataTransport | None,
        runtime_versions: Callable[[], ThemeRuntimeVersions],
        clock: Callable[[], float] = time.monotonic,
    ):
        if channel is not None and transport is None:
            raise ValueError("An enabled theme channel requires a transport")
        self._channel = channel
        self._transport = transport
        self._runtime_versions = runtime_versions
        self._clock = clock
        self._cache: dict[str, _CachedRelease] = {}
        self._lock = threading.Lock()
        self._stopping = False
        self._active_preparations = 0

    def _require_running(self) -> None:
        if self._stopping:
            raise ThemeRemoteError("lifecycle_stopping", "Theme service is stopping")

    def _registration(self, theme_id: str) -> OfficialThemeRegistration:
        if self._channel is None:
            raise ThemeRemoteError("channel_disabled", "Official theme updates are disabled")
        for registration in self._channel.themes:
            if registration.catalog_id == theme_id:
                return registration
        raise ThemeRemoteError("unsupported_theme", "Theme is not registered for remote updates")

    def check_releases(self, force: bool = False) -> dict[str, object]:
        if self._channel is None:
            return {"status": "disabled"}
        with self._lock:
            if self._stopping:
                return self._lifecycle_failure()
            now = float(self._clock())
            cached = [self._cache.get(theme.catalog_id) for theme in self._channel.themes]
            if (
                not force
                and all(entry is not None for entry in cached)
                and all(now - entry.checked_at < _CACHE_SECONDS for entry in cached if entry)
            ):
                releases = [entry.release for entry in cached if entry]
                checked_at = min(entry.checked_at for entry in cached if entry)
                return self._success(releases, checked_at)

        try:
            releases = [self._fetch(theme) for theme in self._channel.themes]
        except ThemeTransportError as error:
            return self._transport_failure(error)
        except ThemeContractError:
            return {
                "status": "recoverable-failure",
                "code": "invalid_descriptor",
                "retryable": True,
            }

        with self._lock:
            if self._stopping:
                return self._lifecycle_failure()
            checked_at = float(self._clock())
            self._cache = {
                release.catalog_id: _CachedRelease(release, checked_at)
                for release in releases
            }
            return self._success(releases, checked_at)

    def prepare_install(
        self,
        theme_id: str,
        expected_version: str,
        themes_root: str | Path,
    ) -> dict[str, object]:
        with self._lock:
            self._require_running()
            registration = self._registration(theme_id)
        try:
            release = self._fetch(registration)
        except ThemeTransportError as error:
            raise ThemeRemoteError(error.code, "Official theme metadata is unavailable") from error
        except ThemeContractError as error:
            raise ThemeRemoteError("invalid_descriptor", "Official theme metadata is invalid") from error
        if release.version != expected_version:
            raise ThemeRemoteError(
                "publication_changed",
                "Published theme version changed after confirmation",
            )
        compatibility = _compatibility(release, self._runtime_versions())
        if compatibility != "compatible":
            raise ThemeRemoteError(
                compatibility.replace("-", "_"),
                "Published theme is incompatible with the running environment",
            )
        with self._lock:
            self._require_running()

        root = Path(themes_root)
        root.parent.mkdir(parents=True, exist_ok=True)
        artifact_path = (
            f"themes/v1/{release.catalog_id}/{release.version}/gallery.zip"
        )
        with tempfile.TemporaryDirectory(
            prefix=".panel-theme-download-",
            dir=root.parent,
        ) as temporary:
            archive = Path(temporary) / "gallery.zip"
            try:
                if self._transport is None:
                    raise ThemeRemoteError(
                        "channel_disabled", "Official theme updates are disabled"
                    )
                self._transport.download_artifact(
                    artifact_path,
                    archive,
                    expected_size=release.artifact.size,
                    expected_sha256=release.artifact.sha256,
                )
            except ThemeTransportError as error:
                raise ThemeRemoteError(error.code, "Official theme download failed") from error
            with self._lock:
                self._require_running()
                self._active_preparations += 1
            descriptor = {
                "schemaVersion": 1,
                "id": release.catalog_id,
                "cssLoaderName": release.css_loader_name,
                "version": release.version,
                "artifact": {
                    "file": "gallery.zip",
                    "size": release.artifact.size,
                    "sha256": release.artifact.sha256,
                },
            }
            try:
                return theme_packages.prepare_theme_archive(
                    archive,
                    descriptor,
                    root,
                    profile=theme_packages.PackageProfile.REMOTE_V1,
                )
            finally:
                with self._lock:
                    self._active_preparations -= 1

    def _fetch(self, registration: OfficialThemeRegistration) -> ThemeRelease:
        if self._transport is None or self._channel is None:
            raise ThemeTransportError("channel_disabled", "Theme channel is disabled")
        release = parse_theme_release(
            self._transport.fetch_metadata(registration.latest_path),
            self._channel.pages_base_url,
        )
        if (
            release.catalog_id != registration.catalog_id
            or release.css_loader_name != registration.css_loader_name
        ):
            raise ThemeContractError("Published theme identity is not registered")
        return release

    def _success(
        self,
        releases: list[ThemeRelease],
        checked_at: float,
    ) -> dict[str, object]:
        runtime = self._runtime_versions()
        return {
            "status": "published",
            "checkedAt": checked_at,
            "themes": [_theme_dto(release, runtime) for release in releases],
        }

    @staticmethod
    def _transport_failure(error: ThemeTransportError) -> dict[str, object]:
        status = (
            "temporarily-unavailable"
            if error.code in {"offline", "timeout", "rate_limited", "http_status"}
            else "recoverable-failure"
        )
        return {"status": status, "code": error.code, "retryable": True}

    @staticmethod
    def _lifecycle_failure() -> dict[str, object]:
        return {
            "status": "recoverable-failure",
            "code": "lifecycle_stopping",
            "retryable": False,
        }

    def close(self) -> None:
        with self._lock:
            self._stopping = True
            self._cache.clear()
