from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

import theme_packages
from theme_remote import OfficialThemeChannel, ThemeRemoteError, ThemeRemoteService, ThemeRuntimeVersions
from theme_transport import ThemeTransportError


PAGES_BASE = "https://example.invalid/panel-de-control"
EARLY_PATH = "themes/v1/early.json"
ARCHIVE = b"published early theme archive"


class Transport:
    def __init__(self, result: bytes | Exception):
        self.result = result
        self.paths: list[str] = []

    def fetch_metadata(self, path: str) -> bytes:
        self.paths.append(path)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def download_artifact(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("early builds are never downloaded")


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def early_json(*, panel: str = "1.0.0", archive: bytes = ARCHIVE) -> bytes:
    theme = {
        "schemaVersion": 1,
        "catalogId": "example-theme",
        "cssLoaderName": "Example Theme",
        "displayName": {"es": "Ejemplo", "en": "Example", "it": "Esempio"},
        "description": {"es": "Desc.", "en": "Desc.", "it": "Desc."},
        "author": "Example Author",
        "tags": [],
        "minimumVersions": {"panel": panel},
        "early": {
            "version": "0.3.0",
            "artifacts": [
                {"version": "0.3.0", "size": len(archive), "sha256": hashlib.sha256(archive).hexdigest()},
                {"version": "0.2.0", "size": 9, "sha256": "c" * 64},
            ],
        },
    }
    return json.dumps({"schemaVersion": 1, "themes": [theme]}).encode()


def service(transport: Transport, clock: Clock | None = None) -> ThemeRemoteService:
    return ThemeRemoteService(
        OfficialThemeChannel(pages_base_url=PAGES_BASE, catalog_path="themes/v1/catalog.json"),
        transport=transport,
        runtime_versions=lambda: ThemeRuntimeVersions(panel="1.0.0"),
        clock=clock or Clock(),
    )


def test_lists_early_themes_from_their_own_file_and_caches_them() -> None:
    clock = Clock()
    transport = Transport(early_json())
    remote = service(transport, clock)
    result = remote.check_early()
    assert result["status"] == "published"
    assert result["themes"][0]["catalogId"] == "example-theme"
    assert result["themes"][0]["earlyVersion"] == "0.3.0"
    assert result["themes"][0]["compatibility"] == "compatible"
    remote.check_early()
    assert transport.paths == [EARLY_PATH]
    clock.now += 16 * 60
    remote.check_early()
    assert transport.paths == [EARLY_PATH, EARLY_PATH]


def test_reports_unavailable_or_invalid_early_lists_without_raising() -> None:
    assert service(Transport(ThemeTransportError("offline", "x"))).check_early()["status"] == "temporarily-unavailable"
    assert service(Transport(b"{}")).check_early()["code"] == "invalid_descriptor"


def test_installs_only_a_byte_exact_published_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def prepare(archive, descriptor, root, *, receipts_path):
        assert Path(archive).read_bytes() == ARCHIVE
        calls.append(descriptor)
        return {"ok": True, "code": "prepared", "transaction": "t"}

    monkeypatch.setattr(theme_packages, "prepare_theme_archive", prepare)
    picked = tmp_path / "hybrid-early-0.3.0.zip"
    picked.write_bytes(ARCHIVE)
    result = service(Transport(early_json())).prepare_early_install(str(picked), tmp_path / "themes", tmp_path / "r.json")
    assert result == {"ok": True, "code": "prepared", "transaction": "t", "catalogId": "example-theme", "version": "0.3.0"}
    assert calls == [{
        "schemaVersion": 1,
        "id": "example-theme",
        "cssLoaderName": "Example Theme",
        "version": "0.3.0",
        "artifact": {"file": "theme.zip", "size": len(ARCHIVE), "sha256": hashlib.sha256(ARCHIVE).hexdigest()},
    }]


def test_rejects_unknown_tampered_incompatible_or_unreadable_archives(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(theme_packages, "prepare_theme_archive", lambda *a, **k: pytest.fail("must not install"))
    tampered = tmp_path / "tampered.zip"
    tampered.write_bytes(ARCHIVE + b"!")
    with pytest.raises(ThemeRemoteError) as error:
        service(Transport(early_json())).prepare_early_install(str(tampered), tmp_path / "themes", tmp_path / "r.json")
    assert error.value.code == "unknown_archive"

    good = tmp_path / "good.zip"
    good.write_bytes(ARCHIVE)
    with pytest.raises(ThemeRemoteError) as error:
        service(Transport(early_json(panel="9.0.0"))).prepare_early_install(str(good), tmp_path / "themes", tmp_path / "r.json")
    assert error.value.code == "incompatible_panel"

    with pytest.raises(ThemeRemoteError) as error:
        service(Transport(ThemeTransportError("offline", "x"))).prepare_early_install(str(good), tmp_path / "themes", tmp_path / "r.json")
    assert error.value.code == "offline"

    link = tmp_path / "link.zip"
    os.symlink(good, link)
    for path in ("relative.zip", str(link), str(tmp_path)):
        with pytest.raises(ThemeRemoteError) as error:
            service(Transport(early_json())).prepare_early_install(path, tmp_path / "themes", tmp_path / "r.json")
        assert error.value.code == "invalid_archive"
