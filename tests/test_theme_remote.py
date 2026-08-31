from __future__ import annotations

import hashlib
import json
import threading
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from theme_remote import (
    OfficialThemeChannel,
    OfficialThemeRegistration,
    ThemeRemoteError,
    ThemeRemoteService,
    ThemeRuntimeVersions,
)
from theme_transport import ThemeTransportError


PAGES_BASE = "https://example.invalid/panel-de-control"
LATEST_PATH = "themes/v1/hooandee-gallery/latest.json"
RELEASE = {
    "schemaVersion": 1,
    "catalogId": "hooandee-gallery",
    "cssLoaderName": "Hooandee Gallery",
    "version": "0.7.9",
    "artifact": {
        "url": f"{PAGES_BASE}/themes/v1/hooandee-gallery/0.7.9/gallery.zip",
        "size": 107_697,
        "sha256": "3af309363a453511d6b00a0b82ac3617bd2791026758f958aba909b877f6bbeb",
    },
    "minimumVersions": {
        "panel": "0.31.4",
        "cssLoader": "2.1.2",
        "cssLoaderBackend": 9,
    },
    "notes": {"es": "Novedades", "en": "Changes", "it": "Novità"},
}


class FakeTransport:
    def __init__(self, result: bytes | Exception):
        self.result = result
        self.paths: list[str] = []
        self.artifacts: dict[str, bytes] = {}
        self.downloads: list[str] = []

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
        self.downloads.append(path)
        content = self.artifacts[path]
        assert len(content) == expected_size
        assert hashlib.sha256(content).hexdigest() == expected_sha256
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


def payload(value: object = RELEASE) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()


def channel() -> OfficialThemeChannel:
    return OfficialThemeChannel(
        pages_base_url=PAGES_BASE,
        themes=(
            OfficialThemeRegistration(
                catalog_id="hooandee-gallery",
                css_loader_name="Hooandee Gallery",
                latest_path=LATEST_PATH,
            ),
        ),
    )


def runtime(**values: object) -> ThemeRuntimeVersions:
    return replace(
        ThemeRuntimeVersions(
            panel="0.31.4",
            css_loader="2.1.2",
            css_loader_backend=9,
        ),
        **values,
    )


def service(
    transport: FakeTransport,
    *,
    clock: Clock | None = None,
    versions: ThemeRuntimeVersions | None = None,
) -> ThemeRemoteService:
    return ThemeRemoteService(
        channel(),
        transport=transport,
        runtime_versions=lambda: versions or runtime(),
        clock=clock or Clock(),
    )


def installable_release(tmp_path: Path) -> tuple[dict[str, object], FakeTransport]:
    archive = tmp_path / "source.zip"
    theme_name = "Hooandee Gallery"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr(
            f"{theme_name}/theme.json",
            json.dumps(
                {
                    "name": theme_name,
                    "display_name": theme_name,
                    "author": "Hooandee",
                    "version": "0.7.9",
                    "manifest_version": 9,
                    "inject": {"tokens.css": ["bigpicture"]},
                    "patches": {},
                }
            ),
        )
        package.writestr(
            f"{theme_name}/panel-theme.json",
            json.dumps(
                {
                    "schemaVersion": 1,
                    "catalogId": "hooandee-gallery",
                    "runtime": {
                        "moduleId": "gallery",
                        "surfaces": [
                            "library",
                            "library-grid",
                            "game-details",
                            "settings",
                        ],
                    },
                }
            ),
        )
        package.writestr(f"{theme_name}/tokens.css", ":root { color: white; }\n")
    blob = archive.read_bytes()
    release = json.loads(json.dumps(RELEASE))
    release["artifact"] = {
        "url": f"{PAGES_BASE}/themes/v1/hooandee-gallery/0.7.9/gallery.zip",
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    transport = FakeTransport(payload(release))
    transport.artifacts["themes/v1/hooandee-gallery/0.7.9/gallery.zip"] = blob
    return release, transport


def test_reports_the_publication_without_exposing_transport_fields() -> None:
    transport = FakeTransport(payload())

    result = service(transport).check_releases()

    assert result == {
        "status": "published",
        "checkedAt": 100.0,
        "themes": [
            {
                "catalogId": "hooandee-gallery",
                "cssLoaderName": "Hooandee Gallery",
                "publishedVersion": "0.7.9",
                "compatibility": "compatible",
                "notes": {"es": "Novedades", "en": "Changes", "it": "Novità"},
            }
        ],
    }
    assert transport.paths == [LATEST_PATH]
    assert "url" not in repr(result)
    assert "sha256" not in repr(result)


def test_reuses_only_successful_metadata_for_fifteen_minutes_and_force_bypasses_it() -> None:
    clock = Clock()
    transport = FakeTransport(payload())
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
    assert transport.paths == [LATEST_PATH, LATEST_PATH, LATEST_PATH]


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (ThemeTransportError("offline", "offline"), "temporarily-unavailable", "offline"),
        (ThemeTransportError("timeout", "timeout"), "temporarily-unavailable", "timeout"),
        (ThemeTransportError("tls_error", "tls"), "recoverable-failure", "tls_error"),
    ],
)
def test_reports_discovery_failure_without_caching_success(
    failure: Exception,
    status: str,
    code: str,
) -> None:
    transport = FakeTransport(failure)
    remote = service(transport)

    assert remote.check_releases() == {"status": status, "code": code, "retryable": True}
    assert remote.check_releases() == {"status": status, "code": code, "retryable": True}
    assert transport.paths == [LATEST_PATH, LATEST_PATH]


@pytest.mark.parametrize(
    ("versions", "compatibility"),
    [
        (runtime(panel="0.31.3"), "incompatible-panel"),
        (runtime(css_loader="2.1.1"), "incompatible-css-loader"),
        (runtime(css_loader_backend=8), "incompatible-css-loader"),
    ],
)
def test_keeps_incompatible_publications_visible_but_not_installable(
    versions: ThemeRuntimeVersions,
    compatibility: str,
) -> None:
    result = service(FakeTransport(payload()), versions=versions).check_releases()

    assert result["themes"][0]["publishedVersion"] == "0.7.9"
    assert result["themes"][0]["compatibility"] == compatibility


def test_reports_disabled_without_constructing_a_transport() -> None:
    remote = ThemeRemoteService(
        None,
        transport=None,
        runtime_versions=lambda: runtime(),
        clock=Clock(),
    )

    assert remote.check_releases() == {"status": "disabled"}


def test_remote_prepare_refetches_downloads_and_uses_the_strict_package_profile(
    tmp_path: Path,
) -> None:
    _, transport = installable_release(tmp_path)
    remote = service(transport)
    themes_root = tmp_path / "homebrew" / "themes"

    result = remote.prepare_install("hooandee-gallery", "0.7.9", themes_root)

    assert result["code"] == "prepared"
    assert result["version"] == "0.7.9"
    assert transport.paths == [LATEST_PATH]
    assert transport.downloads == [
        "themes/v1/hooandee-gallery/0.7.9/gallery.zip"
    ]
    assert not list(themes_root.parent.glob(".panel-theme-download-*"))


def test_remote_prepare_rejects_a_publication_that_changed_after_confirmation(
    tmp_path: Path,
) -> None:
    changed = json.loads(json.dumps(RELEASE))
    changed["version"] = "0.8.0"
    changed["artifact"]["url"] = (
        f"{PAGES_BASE}/themes/v1/hooandee-gallery/0.8.0/gallery.zip"
    )
    transport = FakeTransport(payload(changed))

    with pytest.raises(ThemeRemoteError) as error:
        service(transport).prepare_install(
            "hooandee-gallery",
            "0.7.9",
            tmp_path / "themes",
        )

    assert error.value.code == "publication_changed"
    assert transport.downloads == []


def test_remote_prepare_fails_closed_when_runtime_is_incompatible(tmp_path: Path) -> None:
    _, transport = installable_release(tmp_path)
    remote = service(transport, versions=runtime(css_loader_backend=8))

    with pytest.raises(ThemeRemoteError) as error:
        remote.prepare_install("hooandee-gallery", "0.7.9", tmp_path / "themes")

    assert error.value.code == "incompatible_css_loader"
    assert transport.downloads == []


def test_close_stops_new_checks_and_downloads(tmp_path: Path) -> None:
    _, transport = installable_release(tmp_path)
    remote = service(transport)
    remote.close()

    with pytest.raises(ThemeRemoteError) as error:
        remote.prepare_install("hooandee-gallery", "0.7.9", tmp_path / "themes")

    assert error.value.code == "lifecycle_stopping"
    assert transport.paths == []


def test_close_does_not_wait_for_an_inflight_metadata_request() -> None:
    transport = BlockingTransport(payload())
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


def test_close_during_prepare_metadata_prevents_the_artifact_download(
    tmp_path: Path,
) -> None:
    _, prepared_transport = installable_release(tmp_path)
    transport = BlockingTransport(prepared_transport.result)
    transport.artifacts.update(prepared_transport.artifacts)
    remote = service(transport)
    failures: list[ThemeRemoteError] = []

    def prepare() -> None:
        try:
            remote.prepare_install("hooandee-gallery", "0.7.9", tmp_path / "themes")
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
