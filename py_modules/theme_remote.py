from __future__ import annotations

import base64
import binascii
import json
import math
import re
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import theme_packages
from json_store import atomic_json_save
from theme_remote_contract import (
    ThemeCatalog,
    ThemeCatalogRelease,
    ThemeContractError,
    parse_theme_catalog,
)
from theme_transport import ThemeTransportError


_RUNTIME_SEMVER = re.compile(
    r"^(?:v)?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z.-]+))?$"
)
_SAFE_CATALOG_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STABLE_SEMVER = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
_CACHE_SECONDS = 15 * 60
_MAX_CATALOG_BYTES = 64 * 1024
_MAX_CACHE_FILE_BYTES = 128 * 1024
_CACHE_FIELDS = frozenset({"schemaVersion", "checkedAt", "catalog"})


@dataclass(frozen=True)
class OfficialThemeChannel:
    pages_base_url: str
    catalog_path: str


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


class ThemeCatalogCache(Protocol):
    def load(self) -> object | None: ...

    def save(self, payload: bytes, checked_at: float) -> None: ...


class ThemeCatalogCacheStore:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._lock = threading.Lock()

    @staticmethod
    def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, child in pairs:
            if key in value:
                raise ValueError("duplicate cache field")
            value[key] = child
        return value

    def load(self) -> object | None:
        try:
            with self._lock:
                raw = self._path.read_bytes()
            if not raw or len(raw) > _MAX_CACHE_FILE_BYTES:
                return None
            return json.loads(raw, object_pairs_hook=self._object)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return None

    def save(self, payload: bytes, checked_at: float) -> None:
        record = {
            "schemaVersion": 1,
            "checkedAt": checked_at,
            "catalog": base64.b64encode(payload).decode("ascii"),
        }
        with self._lock:
            atomic_json_save(self._path, record)


@dataclass(frozen=True)
class _CachedCatalog:
    catalog: ThemeCatalog
    checked_at: float


class ThemeRemoteError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _parse_runtime_version(
    value: str,
) -> tuple[str, str, str, tuple[str, ...]] | None:
    if not isinstance(value, str):
        return None
    match = _RUNTIME_SEMVER.fullmatch(value)
    if match is None:
        return None
    return (
        match.group(1),
        match.group(2),
        match.group(3),
        tuple(match.group(4).split(".")) if match.group(4) else (),
    )


def _compare_numeric_component(left: str, right: str) -> int:
    if len(left) != len(right):
        return 1 if len(left) > len(right) else -1
    if left == right:
        return 0
    return 1 if left > right else -1


def _runtime_meets(value: str, minimum: str) -> bool:
    running = _parse_runtime_version(value)
    required = _parse_runtime_version(minimum)
    if running is None or required is None:
        return False
    for running_component, required_component in zip(
        running[:3],
        required[:3],
        strict=True,
    ):
        comparison = _compare_numeric_component(
            running_component,
            required_component,
        )
        if comparison:
            return comparison > 0
    if not required[3]:
        return not running[3]
    if not running[3]:
        return True
    return running[3] >= required[3]


def _compatibility(
    release: ThemeCatalogRelease,
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


def _theme_dto(
    release: ThemeCatalogRelease,
    runtime: ThemeRuntimeVersions,
) -> dict[str, object]:
    result: dict[str, object] = {
        "catalogId": release.catalog_id,
        "cssLoaderName": release.css_loader_name,
        "publishedVersion": release.version,
        "displayName": dict(release.display_name),
        "description": dict(release.description),
        "author": release.author,
        "tags": list(release.tags),
        "notes": dict(release.notes),
        "compatibility": _compatibility(release, runtime),
    }
    if release.exclusive_group is not None:
        result["exclusiveGroup"] = release.exclusive_group
    return result


class ThemeRemoteService:
    def __init__(
        self,
        channel: OfficialThemeChannel | None,
        *,
        transport: ThemeMetadataTransport | None,
        runtime_versions: Callable[[], ThemeRuntimeVersions],
        cache: ThemeCatalogCache | None = None,
        cache_error_logger: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        if channel is not None and transport is None:
            raise ValueError("An enabled theme channel requires a transport")
        self._channel = channel
        self._transport = transport
        self._runtime_versions = runtime_versions
        self._cache_store = cache
        self._cache_error_logger = cache_error_logger
        self._clock = clock
        self._memory: _CachedCatalog | None = None
        self._lock = threading.Lock()
        self._stopping = False
        self._active_preparations = 0

    def _require_running(self) -> None:
        if self._stopping:
            raise ThemeRemoteError("lifecycle_stopping", "Theme service is stopping")

    def check_releases(self, force: bool = False) -> dict[str, object]:
        if self._channel is None:
            return {"status": "disabled"}
        with self._lock:
            if self._stopping:
                return self._lifecycle_failure()
            now = float(self._clock())
            memory = self._memory
            if (
                not force
                and memory is not None
                and math.isfinite(now)
                and 0 <= now - memory.checked_at < _CACHE_SECONDS
            ):
                return self._success(memory.catalog, memory.checked_at)

        try:
            payload, catalog = self._fetch_catalog()
        except ThemeTransportError as error:
            return self._fallback_or_failure(error.code, self._transport_failure(error))
        except ThemeContractError:
            failure = {
                "status": "recoverable-failure",
                "code": "invalid_descriptor",
                "retryable": True,
            }
            return self._fallback_or_failure("invalid_descriptor", failure)

        checked_at = float(self._clock())
        if not math.isfinite(checked_at) or checked_at < 0:
            checked_at = 0.0
        result = self._success(catalog, checked_at)
        with self._lock:
            if self._stopping:
                return self._lifecycle_failure()
            self._memory = _CachedCatalog(catalog, checked_at)

        if self._cache_store is not None:
            try:
                self._cache_store.save(payload, checked_at)
            except Exception as error:  # noqa: BLE001
                if self._cache_error_logger is not None:
                    self._cache_error_logger(type(error).__name__)
        return result

    def prepare_install(
        self,
        theme_id: str,
        expected_version: str,
        themes_root: str | Path,
        receipts_path: str | Path,
    ) -> dict[str, object]:
        with self._lock:
            self._require_running()
        if (
            not isinstance(theme_id, str)
            or _SAFE_CATALOG_ID.fullmatch(theme_id) is None
        ):
            raise ThemeRemoteError("unsupported_theme", "Theme id is invalid")
        if (
            not isinstance(expected_version, str)
            or _STABLE_SEMVER.fullmatch(expected_version) is None
        ):
            raise ThemeRemoteError("invalid_descriptor", "Theme version is invalid")

        try:
            _, catalog = self._fetch_catalog()
        except ThemeTransportError as error:
            raise ThemeRemoteError(error.code, "Official theme catalog is unavailable") from error
        except ThemeContractError as error:
            raise ThemeRemoteError("invalid_descriptor", "Official theme catalog is invalid") from error

        release = next(
            (candidate for candidate in catalog.themes if candidate.catalog_id == theme_id),
            None,
        )
        if release is None:
            raise ThemeRemoteError("unsupported_theme", "Theme is not in the live catalog")
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
        artifact_path = f"themes/v1/{release.catalog_id}/{release.version}/theme.zip"
        with tempfile.TemporaryDirectory(
            prefix=".panel-theme-download-",
            dir=root.parent,
        ) as temporary:
            archive = Path(temporary) / "theme.zip"
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
                    "file": "theme.zip",
                    "size": release.artifact.size,
                    "sha256": release.artifact.sha256,
                },
            }
            try:
                return theme_packages.prepare_theme_archive(
                    archive,
                    descriptor,
                    root,
                    receipts_path=receipts_path,
                )
            finally:
                with self._lock:
                    self._active_preparations -= 1

    def _fetch_catalog(self) -> tuple[bytes, ThemeCatalog]:
        if self._transport is None or self._channel is None:
            raise ThemeTransportError("channel_disabled", "Theme channel is disabled")
        payload = self._transport.fetch_metadata(self._channel.catalog_path)
        return payload, parse_theme_catalog(payload, self._channel.pages_base_url)

    def _load_persisted(self) -> _CachedCatalog | None:
        if self._cache_store is None or self._channel is None:
            return None
        try:
            record = self._cache_store.load()
            if not isinstance(record, dict) or frozenset(record) != _CACHE_FIELDS:
                return None
            if record.get("schemaVersion") != 1 or isinstance(
                record.get("schemaVersion"), bool
            ):
                return None
            checked_at = record.get("checkedAt")
            encoded = record.get("catalog")
            if (
                not isinstance(checked_at, (int, float))
                or isinstance(checked_at, bool)
                or not math.isfinite(float(checked_at))
                or float(checked_at) < 0
                or not isinstance(encoded, str)
                or len(encoded) > ((_MAX_CATALOG_BYTES + 2) // 3) * 4
            ):
                return None
            payload = base64.b64decode(encoded, validate=True)
            if base64.b64encode(payload).decode("ascii") != encoded:
                return None
            parsed = parse_theme_catalog(payload, self._channel.pages_base_url)
            return _CachedCatalog(parsed, float(checked_at))
        except (
            binascii.Error,
            ThemeContractError,
            UnicodeEncodeError,
            ValueError,
        ):
            return None
        except Exception as error:  # noqa: BLE001
            if self._cache_error_logger is not None:
                self._cache_error_logger(type(error).__name__)
            return None

    def _fallback_or_failure(
        self,
        code: str,
        failure: dict[str, object],
    ) -> dict[str, object]:
        with self._lock:
            if self._stopping:
                return self._lifecycle_failure()
            memory = self._memory
        cached = memory if memory is not None else self._load_persisted()
        if cached is None:
            return failure
        result = self._success(cached.catalog, cached.checked_at)
        result.update({"status": "cached", "code": code, "retryable": True})
        return result

    def _success(
        self,
        catalog: ThemeCatalog,
        checked_at: float,
    ) -> dict[str, object]:
        runtime = self._runtime_versions()
        return {
            "status": "published",
            "checkedAt": checked_at,
            "themes": [_theme_dto(release, runtime) for release in catalog.themes],
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
            self._memory = None
