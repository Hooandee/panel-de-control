from __future__ import annotations

import json

import pytest

from theme_remote_contract import ThemeContractError, parse_theme_release


PAGES_BASE = "https://example.invalid/panel-de-control"
VALID_RELEASE = {
    "schemaVersion": 1,
    "catalogId": "hooandee-gallery",
    "cssLoaderName": "Hooandee Gallery",
    "version": "0.7.9",
    "artifact": {
        "url": (
            f"{PAGES_BASE}/themes/v1/hooandee-gallery/0.7.9/gallery.zip"
        ),
        "size": 107_697,
        "sha256": "3af309363a453511d6b00a0b82ac3617bd2791026758f958aba909b877f6bbeb",
    },
    "minimumVersions": {
        "panel": "0.31.4",
        "cssLoader": "2.1.2",
        "cssLoaderBackend": 9,
    },
    "notes": {
        "es": "Actualización de prueba",
        "en": "Test update",
        "it": "Aggiornamento di prova",
    },
}


def payload(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()


def changed(**values: object) -> dict[str, object]:
    return {**VALID_RELEASE, **values}


def test_parses_the_exact_public_v1_release() -> None:
    release = parse_theme_release(payload(VALID_RELEASE), PAGES_BASE)

    assert release.catalog_id == "hooandee-gallery"
    assert release.css_loader_name == "Hooandee Gallery"
    assert release.version == "0.7.9"
    assert release.artifact.size == 107_697
    assert release.minimum_versions.css_loader_backend == 9
    assert dict(release.notes) == VALID_RELEASE["notes"]


@pytest.mark.parametrize(
    "invalid",
    [
        changed(schemaVersion=2),
        changed(unexpected=True),
        changed(catalogId="../gallery"),
        changed(cssLoaderName="../Gallery"),
        changed(version="0.7.9-beta.1"),
        changed(version="v0.7.9"),
        changed(
            artifact={
                **VALID_RELEASE["artifact"],
                "url": "https://attacker.invalid/gallery.zip",
            }
        ),
        changed(
            artifact={
                **VALID_RELEASE["artifact"],
                "url": (
                    f"{PAGES_BASE}/themes/v1/hooandee-gallery/0.8.0/gallery.zip"
                ),
            }
        ),
        changed(artifact={**VALID_RELEASE["artifact"], "size": True}),
        changed(artifact={**VALID_RELEASE["artifact"], "size": 64 * 1024 * 1024 + 1}),
        changed(artifact={**VALID_RELEASE["artifact"], "sha256": "ABC123"}),
        changed(
            minimumVersions={
                **VALID_RELEASE["minimumVersions"],
                "cssLoaderBackend": True,
            }
        ),
        changed(notes={"de": "Nicht erlaubt"}),
        changed(notes={"es": "x" * 1_001}),
    ],
)
def test_rejects_malformed_or_escaped_release_fields(invalid: object) -> None:
    with pytest.raises(ThemeContractError):
        parse_theme_release(payload(invalid), PAGES_BASE)


@pytest.mark.parametrize(
    "invalid",
    [
        b"\xff",
        b"[]",
        b'{"schemaVersion":1,"schemaVersion":1}',
        b"{" + b'"padding":"x",' * 7_000 + b'"schemaVersion":1}',
    ],
)
def test_rejects_invalid_duplicate_or_oversized_json(invalid: bytes) -> None:
    with pytest.raises(ThemeContractError):
        parse_theme_release(invalid, PAGES_BASE)
