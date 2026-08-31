from __future__ import annotations

import base64
import hashlib
import json
import math
import threading
from dataclasses import replace
from pathlib import Path

import pytest

import theme_packages
from theme_remote import (
    OfficialThemeChannel,
    ThemeCatalogCacheStore,
    ThemeRemoteError,
    ThemeRemoteService,
    ThemeRuntimeVersions,
)
from theme_transport import ThemeTransportError


PAGES_BASE = "https://example.invalid/panel-de-control"
CATALOG_PATH = "themes/v1/catalog.json"


def release(
    catalog_id: str = "example-theme",
    version: str = "1.2.3",
    *,
    css_loader_name: str = "Example Theme",
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "catalogId": catalog_id,
        "cssLoaderName": css_loader_name,
        "version": version,
        "displayName": {
            "es": f"Ejemplo {catalog_id}",
            "en": f"Example {catalog_id}",
            "it": f"Esempio {catalog_id}",
        },
        "description": {
            "es": "Descripción publicada",
            "en": "Published description",
            "it": "Descrizione pubblicata",
        },
        "author": "Example Author",
        "tags": ["dark", "compact"],
        "exclusiveGroup": "interface",
        "artifact": {
            "url": f"{PAGES_BASE}/themes/v1/{catalog_id}/{version}/theme.zip",
            "size": 321,
            "sha256": "a" * 64,
        },
        "minimumVersions": {
            "panel": "1.0.0",
            "cssLoader": "2.1.0",
            "cssLoaderBackend": 9,
        },
        "notes": {"es": "Novedades", "en": "Changes", "it": "Novità"},
    }


def catalog(*releases: dict[str, object]) -> bytes:
    return json.dumps(
        {"schemaVersion": 1, "themes": list(releases)},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


class FakeTransport:
    def __init__(self, result: bytes | Exception):
        self.result = result
        self.paths: list[str] = []
        self.artifacts: dict[str, bytes] = {}
        self.downloads: list[tuple[str, str, int, str]] = []

    def fetch_metadata(self, path: str) -> bytes:
        self.paths.append(path)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def download_artifact(
        self,
        path: str,
        destination: str | Path,
        *,
        expected_size: int,
        expected_sha256: str,
    ) -> object:
        content = self.artifacts[path]
        self.downloads.append(
            (path, Path(destination).name, expected_size, expected_sha256)
        )
        Path(destination).write_bytes(content)
        return object()


class BlockingTransport(FakeTransport):
    def __init__(self, result: bytes):
        super().__init__(result)
        self.started = threading.Event()
        self.release = threading.Event()

    def fetch_metadata(self, path: str) -> bytes:
        self.started.set()
        if not self.release.wait(2):
            raise AssertionError("metadata fetch was not released")
        return super().fetch_metadata(path)


class Clock:
    def __init__(self, value: float = 100.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


class MemoryCache:
    def __init__(self, value: object | None = None):
        self.value = value
        self.saves: list[tuple[bytes, float]] = []

    def load(self) -> object | None:
        return self.value

    def save(self, payload: bytes, checked_at: float) -> None:
        self.saves.append((payload, checked_at))
        self.value = {
            "schemaVersion": 1,
            "checkedAt": checked_at,
            "catalog": base64.b64encode(payload).decode("ascii"),
        }


def channel() -> OfficialThemeChannel:
    return OfficialThemeChannel(
        pages_base_url=PAGES_BASE,
        catalog_path=CATALOG_PATH,
    )


def runtime(**values: object) -> ThemeRuntimeVersions:
    return replace(
        ThemeRuntimeVersions(
            panel="1.0.0",
            css_loader="2.1.0",
            css_loader_backend=9,
        ),
        **values,
    )


def service(
    transport: FakeTransport,
    *,
    clock: Clock | None = None,
    versions: ThemeRuntimeVersions | None = None,
    cache: object | None = None,
) -> ThemeRemoteService:
    return ThemeRemoteService(
        channel(),
        transport=transport,
        runtime_versions=lambda: versions or runtime(),
        cache=cache,
        clock=clock or Clock(),
    )


def cached_record(payload: bytes, checked_at: float = 50.0) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "checkedAt": checked_at,
        "catalog": base64.b64encode(payload).decode("ascii"),
    }


def test_reports_dynamic_catalog_without_exposing_transport_fields() -> None:
    first = release()
    second = release("second-theme", "4.5.6", css_loader_name="Second Theme")
    transport = FakeTransport(catalog(first, second))

    result = service(transport).check_releases()

    assert result == {
        "status": "published",
        "checkedAt": 100.0,
        "themes": [
            {
                "catalogId": "example-theme",
                "cssLoaderName": "Example Theme",
                "publishedVersion": "1.2.3",
                "displayName": first["displayName"],
                "description": first["description"],
                "author": "Example Author",
                "tags": ["dark", "compact"],
                "exclusiveGroup": "interface",
                "notes": first["notes"],
                "compatibility": "compatible",
            },
            {
                "catalogId": "second-theme",
                "cssLoaderName": "Second Theme",
                "publishedVersion": "4.5.6",
                "displayName": second["displayName"],
                "description": second["description"],
                "author": "Example Author",
                "tags": ["dark", "compact"],
                "exclusiveGroup": "interface",
                "notes": second["notes"],
                "compatibility": "compatible",
            },
        ],
    }
    assert transport.paths == [CATALOG_PATH]
    assert "url" not in repr(result)
    assert "sha256" not in repr(result)
    assert "size" not in repr(result)


def test_accepts_an_empty_catalog() -> None:
    assert service(FakeTransport(catalog())).check_releases() == {
        "status": "published",
        "checkedAt": 100.0,
        "themes": [],
    }


def test_reuses_only_successful_catalog_for_fifteen_minutes_and_force_bypasses_it() -> None:
    clock = Clock()
    transport = FakeTransport(catalog(release()))
    remote = service(transport, clock=clock)

    first = remote.check_releases()
    clock.value += 899
    cached = remote.check_releases()
    forced = remote.check_releases(force=True)
    clock.value += 901
    expired = remote.check_releases()

    assert first["checkedAt"] == cached["checkedAt"]
    assert forced["checkedAt"] == 999.0
    assert expired["checkedAt"] == 1_900.0
    assert transport.paths == [CATALOG_PATH, CATALOG_PATH, CATALOG_PATH]


@pytest.mark.parametrize(
    ("versions", "compatibility"),
    [
        (runtime(panel="0.9.9"), "incompatible-panel"),
        (runtime(css_loader="2.0.9"), "incompatible-css-loader"),
        (runtime(css_loader_backend=8), "incompatible-css-loader"),
        (runtime(css_loader="", css_loader_backend=0), "incompatible-css-loader"),
    ],
)
def test_keeps_incompatible_publications_visible(
    versions: ThemeRuntimeVersions,
    compatibility: str,
) -> None:
    result = service(
        FakeTransport(catalog(release())),
        versions=versions,
    ).check_releases()

    assert result["themes"][0]["compatibility"] == compatibility


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (ThemeTransportError("offline", "offline"), "temporarily-unavailable", "offline"),
        (ThemeTransportError("timeout", "timeout"), "temporarily-unavailable", "timeout"),
        (ThemeTransportError("tls_error", "tls"), "recoverable-failure", "tls_error"),
    ],
)
def test_live_failures_remain_typed_and_are_not_cached(
    failure: Exception,
    status: str,
    code: str,
) -> None:
    transport = FakeTransport(failure)
    remote = service(transport)

    assert remote.check_releases() == {
        "status": status,
        "code": code,
        "retryable": True,
    }
    assert remote.check_releases() == {
        "status": status,
        "code": code,
        "retryable": True,
    }
    assert transport.paths == [CATALOG_PATH, CATALOG_PATH]


def test_persists_exact_validated_live_catalog() -> None:
    raw = catalog(release())
    cache = MemoryCache()

    result = service(FakeTransport(raw), cache=cache).check_releases()

    assert result["status"] == "published"
    assert cache.saves == [(raw, 100.0)]


def test_process_restart_uses_valid_persisted_catalog_only_after_live_failure() -> None:
    raw = catalog(release())
    cache = MemoryCache(cached_record(raw, checked_at=42.0))
    remote = service(
        FakeTransport(ThemeTransportError("offline", "offline")),
        cache=cache,
    )

    result = remote.check_releases()

    assert result["status"] == "cached"
    assert result["checkedAt"] == 42.0
    assert result["code"] == "offline"
    assert result["retryable"] is True
    assert result["themes"][0]["catalogId"] == "example-theme"
    assert cache.saves == []


@pytest.mark.parametrize(
    "bad_cache",
    [
        {"schemaVersion": 1, "checkedAt": 10.0, "catalog": "%%%"},
        {
            "schemaVersion": 1,
            "checkedAt": math.inf,
            "catalog": base64.b64encode(catalog(release())).decode(),
        },
        {
            "schemaVersion": 1,
            "checkedAt": 10.0,
            "catalog": base64.b64encode(b"x" * (64 * 1024 + 1)).decode(),
        },
        {**cached_record(catalog(release())), "unexpected": True},
        cached_record(b'{"schemaVersion":1,"themes":"tampered"}'),
    ],
)
def test_invalid_persisted_cache_never_masks_live_failure(bad_cache: object) -> None:
    remote = service(
        FakeTransport(ThemeTransportError("offline", "offline")),
        cache=MemoryCache(bad_cache),
    )

    assert remote.check_releases() == {
        "status": "temporarily-unavailable",
        "code": "offline",
        "retryable": True,
    }


def test_invalid_live_catalog_does_not_replace_prior_cache() -> None:
    previous = catalog(release())
    cache = MemoryCache(cached_record(previous, checked_at=42.0))

    result = service(FakeTransport(b"{}"), cache=cache).check_releases()

    assert result["status"] == "cached"
    assert result["code"] == "invalid_descriptor"
    assert result["themes"][0]["catalogId"] == "example-theme"
    assert cache.saves == []


def test_cache_persistence_failure_does_not_hide_valid_live_catalog() -> None:
    class FailingCache(MemoryCache):
        def save(self, payload: bytes, checked_at: float) -> None:
            raise OSError("read only")

    result = service(
        FakeTransport(catalog(release())),
        cache=FailingCache(),
    ).check_releases()

    assert result["status"] == "published"
    assert result["themes"][0]["catalogId"] == "example-theme"


def test_atomic_cache_store_round_trips_exact_catalog(tmp_path: Path) -> None:
    path = tmp_path / "settings" / "theme-catalog-cache.json"
    store = ThemeCatalogCacheStore(path)
    raw = catalog(release())

    store.save(raw, 123.5)

    assert store.load() == cached_record(raw, checked_at=123.5)
    assert not list(path.parent.glob("*.tmp"))


def test_install_fetches_a_fresh_catalog_and_uses_neutral_remote_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_release = release()
    artifact = b"neutral theme archive"
    raw_release["artifact"] = {
        "url": f"{PAGES_BASE}/themes/v1/example-theme/1.2.3/theme.zip",
        "size": len(artifact),
        "sha256": hashlib.sha256(artifact).hexdigest(),
    }
    transport = FakeTransport(catalog(raw_release))
    artifact_path = "themes/v1/example-theme/1.2.3/theme.zip"
    transport.artifacts[artifact_path] = artifact
    calls: list[tuple[str, dict[str, object], Path, object]] = []

    def prepare(archive, descriptor, root, *, profile):
        calls.append((Path(archive).name, descriptor, Path(root), profile))
        return {
            "ok": True,
            "code": "prepared",
            "theme_id": descriptor["id"],
            "version": descriptor["version"],
        }

    monkeypatch.setattr(theme_packages, "prepare_theme_archive", prepare)
    remote = service(transport)
    assert remote.check_releases()["status"] == "published"

    result = remote.prepare_install(
        "example-theme",
        "1.2.3",
        tmp_path / "themes",
    )

    assert result["code"] == "prepared"
    assert transport.paths == [CATALOG_PATH, CATALOG_PATH]
    assert transport.downloads == [
        (
            artifact_path,
            "theme.zip",
            len(artifact),
            hashlib.sha256(artifact).hexdigest(),
        )
    ]
    assert calls == [
        (
            "theme.zip",
            {
                "schemaVersion": 1,
                "id": "example-theme",
                "cssLoaderName": "Example Theme",
                "version": "1.2.3",
                "artifact": {
                    "file": "theme.zip",
                    "size": len(artifact),
                    "sha256": hashlib.sha256(artifact).hexdigest(),
                },
            },
            tmp_path / "themes",
            theme_packages.PackageProfile.REMOTE_V1,
        )
    ]


@pytest.mark.parametrize(
    ("live_releases", "expected_version", "code"),
    [
        ([], "1.2.3", "unsupported_theme"),
        ([release(version="1.2.4")], "1.2.3", "publication_changed"),
    ],
)
def test_install_rejects_catalog_removal_or_version_change_before_download(
    tmp_path: Path,
    live_releases: list[dict[str, object]],
    expected_version: str,
    code: str,
) -> None:
    transport = FakeTransport(catalog(*live_releases))

    with pytest.raises(ThemeRemoteError) as error:
        service(transport).prepare_install(
            "example-theme",
            expected_version,
            tmp_path / "themes",
        )

    assert error.value.code == code
    assert transport.downloads == []


def test_install_never_uses_persisted_cache_as_authority(tmp_path: Path) -> None:
    cache = MemoryCache(cached_record(catalog(release())))
    transport = FakeTransport(ThemeTransportError("offline", "offline"))

    with pytest.raises(ThemeRemoteError) as error:
        service(transport, cache=cache).prepare_install(
            "example-theme",
            "1.2.3",
            tmp_path / "themes",
        )

    assert error.value.code == "offline"
    assert transport.downloads == []


def test_install_fails_closed_when_live_runtime_is_incompatible(tmp_path: Path) -> None:
    transport = FakeTransport(catalog(release()))

    with pytest.raises(ThemeRemoteError) as error:
        service(
            transport,
            versions=runtime(css_loader_backend=8),
        ).prepare_install("example-theme", "1.2.3", tmp_path / "themes")

    assert error.value.code == "incompatible_css_loader"
    assert transport.downloads == []


def test_close_stops_new_checks_and_installs(tmp_path: Path) -> None:
    transport = FakeTransport(catalog(release()))
    remote = service(transport)
    remote.close()

    assert remote.check_releases() == {
        "status": "recoverable-failure",
        "code": "lifecycle_stopping",
        "retryable": False,
    }
    with pytest.raises(ThemeRemoteError) as error:
        remote.prepare_install("example-theme", "1.2.3", tmp_path / "themes")
    assert error.value.code == "lifecycle_stopping"
    assert transport.paths == []


def test_close_does_not_wait_for_an_inflight_catalog_request() -> None:
    transport = BlockingTransport(catalog(release()))
    remote = service(transport)
    result: list[dict[str, object]] = []
    checked = threading.Thread(
        target=lambda: result.append(remote.check_releases()),
        daemon=True,
    )
    checked.start()
    assert transport.started.wait(1)

    closed = threading.Event()
    closing = threading.Thread(
        target=lambda: (remote.close(), closed.set()),
        daemon=True,
    )
    closing.start()
    try:
        assert closed.wait(0.2)
    finally:
        transport.release.set()
        checked.join(2)
        closing.join(2)

    assert result == [{
        "status": "recoverable-failure",
        "code": "lifecycle_stopping",
        "retryable": False,
    }]


def test_close_during_install_catalog_fetch_prevents_artifact_download(
    tmp_path: Path,
) -> None:
    transport = BlockingTransport(catalog(release()))
    remote = service(transport)
    failures: list[ThemeRemoteError] = []

    def prepare() -> None:
        try:
            remote.prepare_install("example-theme", "1.2.3", tmp_path / "themes")
        except ThemeRemoteError as error:
            failures.append(error)

    preparing = threading.Thread(target=prepare, daemon=True)
    preparing.start()
    assert transport.started.wait(1)
    remote.close()
    transport.release.set()
    preparing.join(2)

    assert [error.code for error in failures] == ["lifecycle_stopping"]
    assert transport.downloads == []
