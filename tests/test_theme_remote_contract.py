from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from theme_remote_contract import (
    ThemeCatalog,
    ThemeCatalogRelease,
    ThemeContractError,
    parse_theme_catalog,
    parse_theme_release,
)


PAGES_BASE = "https://example.invalid/panel-de-control"
VALID_RELEASE = {
    "schemaVersion": 1,
    "catalogId": "example-theme",
    "cssLoaderName": "Example Theme",
    "version": "1.2.3",
    "displayName": {
        "es": "Tema de ejemplo",
        "en": "Example Theme",
        "it": "Tema di esempio",
    },
    "description": {
        "es": "Una descripción neutral.",
        "en": "A neutral description.",
        "it": "Una descrizione neutrale.",
    },
    "author": "Example Author",
    "tags": ["minimal", "dark-mode"],
    "artifact": {
        "url": f"{PAGES_BASE}/themes/v1/example-theme/1.2.3/theme.zip",
        "size": 12_345,
        "sha256": "a" * 64,
    },
    "minimumVersions": {
        "panel": "1.0.0",
        "cssLoader": "2.1.2",
        "cssLoaderBackend": 9,
    },
    "exclusiveGroup": "color-system",
    "notes": {
        "es": "Actualización de ejemplo",
        "en": "Example update",
        "it": "Aggiornamento di esempio",
    },
}


def payload(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def changed(**values: object) -> dict[str, object]:
    return {**VALID_RELEASE, **values}


def catalog(*releases: object, **values: object) -> dict[str, object]:
    return {"schemaVersion": 1, "themes": list(releases), **values}


def test_parses_the_exact_public_v1_release_as_immutable_data() -> None:
    release = parse_theme_release(payload(VALID_RELEASE), PAGES_BASE)

    assert isinstance(release, ThemeCatalogRelease)
    assert release.catalog_id == "example-theme"
    assert release.css_loader_name == "Example Theme"
    assert release.version == "1.2.3"
    assert dict(release.display_name) == VALID_RELEASE["displayName"]
    assert dict(release.description) == VALID_RELEASE["description"]
    assert release.author == "Example Author"
    assert release.tags == ("minimal", "dark-mode")
    assert release.exclusive_group == "color-system"
    assert release.artifact.size == 12_345
    assert release.minimum_versions.css_loader_backend == 9
    assert dict(release.notes) == VALID_RELEASE["notes"]
    with pytest.raises(FrozenInstanceError):
        release.version = "1.2.4"  # type: ignore[misc]
    with pytest.raises(TypeError):
        release.display_name["en"] = "Changed"  # type: ignore[index]


def test_parses_a_catalog_with_unique_immutable_releases() -> None:
    second = changed(
        catalogId="second-theme",
        cssLoaderName="Second Theme",
        artifact={
            **VALID_RELEASE["artifact"],
            "url": f"{PAGES_BASE}/themes/v1/second-theme/1.2.3/theme.zip",
        },
    )

    result = parse_theme_catalog(
        payload(catalog(VALID_RELEASE, second)),
        PAGES_BASE,
    )

    assert isinstance(result, ThemeCatalog)
    assert result.schema_version == 1
    assert isinstance(result.themes, tuple)
    assert [release.catalog_id for release in result.themes] == [
        "example-theme",
        "second-theme",
    ]
    with pytest.raises(FrozenInstanceError):
        result.themes = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    "invalid",
    [
        {"schemaVersion": 2, "themes": []},
        {"schemaVersion": True, "themes": []},
        {"schemaVersion": 1},
        {"schemaVersion": 1, "themes": [], "unexpected": True},
        {"schemaVersion": 1, "themes": {}},
        {"schemaVersion": 1, "themes": [VALID_RELEASE, VALID_RELEASE]},
        {
            "schemaVersion": 1,
            "themes": [
                changed(
                    catalogId=f"theme-{index}",
                    artifact={
                        **VALID_RELEASE["artifact"],
                        "url": (
                            f"{PAGES_BASE}/themes/v1/theme-{index}/1.2.3/theme.zip"
                        ),
                    },
                )
                for index in range(33)
            ],
        },
    ],
)
def test_rejects_invalid_catalog_shape_count_or_duplicate_ids(invalid: object) -> None:
    with pytest.raises(ThemeContractError):
        parse_theme_catalog(payload(invalid), PAGES_BASE)


def test_rejects_catalog_bytes_above_the_public_limit() -> None:
    oversized = b'{"schemaVersion":1,"themes":[]}' + b" " * (64 * 1024)

    with pytest.raises(ThemeContractError, match="size"):
        parse_theme_catalog(oversized, PAGES_BASE)


@pytest.mark.parametrize(
    "invalid",
    [
        changed(unexpected=True),
        {key: value for key, value in VALID_RELEASE.items() if key != "author"},
        changed(schemaVersion=2),
        changed(schemaVersion=True),
        changed(catalogId="../example-theme"),
        changed(catalogId="Example-Theme"),
        changed(cssLoaderName="../Example Theme"),
        changed(cssLoaderName="Example\\Theme"),
        changed(cssLoaderName=" "),
        changed(cssLoaderName="x" * 129),
        changed(version="1.2.3-beta.1"),
        changed(version="v1.2.3"),
        changed(version="01.2.3"),
        changed(author=" "),
        changed(author="á" * 81),
        changed(tags=["valid"] * 9),
        changed(tags=["not_valid"]),
        changed(tags="minimal"),
        changed(exclusiveGroup="not_valid"),
        changed(exclusiveGroup=None),
        changed(notes={"es": "Nota", "en": "Note"}),
        changed(notes={"es": "Nota", "en": "Note", "it": " "}),
        changed(notes={"es": "x" * 1_001, "en": "Note", "it": "Nota"}),
    ],
)
def test_rejects_unknown_missing_or_invalid_release_identity_fields(
    invalid: object,
) -> None:
    with pytest.raises(ThemeContractError):
        parse_theme_release(payload(invalid), PAGES_BASE)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("displayName", {"es": "Tema", "en": "Theme"}),
        ("displayName", {"es": "Tema", "en": "Theme", "it": "Tema", "de": "Thema"}),
        ("displayName", {"es": " ", "en": "Theme", "it": "Tema"}),
        ("displayName", {"es": "😀" * 81, "en": "Theme", "it": "Tema"}),
        (
            "description",
            {"es": "Descripción", "en": "Description", "it": "😀" * 401},
        ),
    ],
)
def test_rejects_non_exact_empty_or_overlong_localized_presentation(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ThemeContractError):
        parse_theme_release(payload(changed(**{field: value})), PAGES_BASE)


@pytest.mark.parametrize(
    "invalid_artifact",
    [
        {**VALID_RELEASE["artifact"], "unexpected": True},
        {**VALID_RELEASE["artifact"], "url": "https://attacker.invalid/theme.zip"},
        {
            **VALID_RELEASE["artifact"],
            "url": f"{PAGES_BASE}/themes/v1/example-theme/1.2.4/theme.zip",
        },
        {
            **VALID_RELEASE["artifact"],
            "url": f"{PAGES_BASE}/themes/v1/example-theme/1.2.3/release.json",
        },
        {
            **VALID_RELEASE["artifact"],
            "url": f"{PAGES_BASE}/themes/v1/example%2dtheme/1.2.3/theme.zip",
        },
        {**VALID_RELEASE["artifact"], "size": True},
        {**VALID_RELEASE["artifact"], "size": 0},
        {**VALID_RELEASE["artifact"], "size": 64 * 1024 * 1024 + 1},
        {**VALID_RELEASE["artifact"], "sha256": "A" * 64},
    ],
)
def test_rejects_artifacts_outside_the_exact_immutable_path(
    invalid_artifact: object,
) -> None:
    with pytest.raises(ThemeContractError):
        parse_theme_release(
            payload(changed(artifact=invalid_artifact)),
            PAGES_BASE,
        )


@pytest.mark.parametrize(
    "minimum_versions",
    [
        {**VALID_RELEASE["minimumVersions"], "unexpected": True},
        {**VALID_RELEASE["minimumVersions"], "panel": "v1.0.0"},
        {**VALID_RELEASE["minimumVersions"], "cssLoader": "2.1.2-beta.1"},
        {**VALID_RELEASE["minimumVersions"], "cssLoaderBackend": True},
        {**VALID_RELEASE["minimumVersions"], "cssLoaderBackend": 0},
    ],
)
def test_rejects_invalid_minimum_versions(minimum_versions: object) -> None:
    with pytest.raises(ThemeContractError):
        parse_theme_release(
            payload(changed(minimumVersions=minimum_versions)),
            PAGES_BASE,
        )


@pytest.mark.parametrize(
    "invalid",
    [
        b"\xff",
        b"[]",
        b'{"schemaVersion":1,"schemaVersion":1,"themes":[]}',
        (
            b'{"schemaVersion":1,"themes":[{"schemaVersion":1,'
            b'"catalogId":"example-theme","catalogId":"second-theme"}]}'
        ),
    ],
)
def test_rejects_invalid_utf8_root_types_and_duplicate_json_keys(invalid: bytes) -> None:
    with pytest.raises(ThemeContractError):
        parse_theme_catalog(invalid, PAGES_BASE)


def test_rejects_json_escaped_catalog_id_even_when_it_decodes_to_a_valid_id() -> None:
    encoded = payload(catalog(VALID_RELEASE)).replace(
        b'"example-theme"',
        b'"example\\u002dtheme"',
        1,
    )

    with pytest.raises(ThemeContractError):
        parse_theme_catalog(encoded, PAGES_BASE)
