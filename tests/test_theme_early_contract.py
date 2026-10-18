from __future__ import annotations

import json

import pytest

from theme_remote_contract import ThemeContractError, parse_theme_early_catalog


VALID_EARLY = {
    "schemaVersion": 1,
    "catalogId": "example-theme",
    "cssLoaderName": "Example Theme",
    "displayName": {"es": "Tema de ejemplo", "en": "Example Theme", "it": "Tema di esempio"},
    "description": {"es": "Una descripción.", "en": "A description.", "it": "Una descrizione."},
    "author": "Example Author",
    "tags": ["minimal"],
    "minimumVersions": {"panel": "1.0.0"},
    "early": {
        "version": "0.3.0",
        "artifacts": [
            {"version": "0.3.0", "size": 1234, "sha256": "b" * 64},
            {"version": "0.2.0", "size": 1200, "sha256": "c" * 64},
        ],
    },
}


def payload(*themes: object) -> bytes:
    return json.dumps({"schemaVersion": 1, "themes": list(themes)}).encode("utf-8")


def changed(**values: object) -> dict[str, object]:
    return {**VALID_EARLY, **values}


def test_parses_early_themes_with_their_accepted_artifacts() -> None:
    catalog = parse_theme_early_catalog(payload(VALID_EARLY))
    theme = catalog.themes[0]
    assert theme.catalog_id == "example-theme"
    assert theme.css_loader_name == "Example Theme"
    assert theme.version == "0.3.0"
    assert [(a.version, a.size, a.sha256) for a in theme.artifacts] == [
        ("0.3.0", 1234, "b" * 64),
        ("0.2.0", 1200, "c" * 64),
    ]
    assert theme.minimum_versions.panel == "1.0.0"
    assert dict(theme.display_name)["en"] == "Example Theme"


@pytest.mark.parametrize(
    "theme",
    [
        changed(extra=True),
        changed(early={"version": "0.3.0", "artifacts": []}),
        changed(early={"version": "0.4.0", "artifacts": VALID_EARLY["early"]["artifacts"]}),
        changed(early={"version": "0.3.0", "artifacts": [{"version": "0.3.0", "size": 1, "sha256": "B" * 64}]}),
        changed(early={"version": "0.3.0", "artifacts": [{"version": "0.3.0", "size": 0, "sha256": "b" * 64}]}),
        changed(early={"version": "0.3.0", "artifacts": [{"version": "0.3.0", "size": 1, "sha256": "b" * 64, "url": "x"}]}),
        changed(early={"version": "0.3.0", "artifacts": [{"version": "0.3.0", "size": 1, "sha256": "b" * 64}] * 2}),
        changed(early={"version": "0.3.0", "artifacts": [{"version": f"0.{i}.0", "size": 1, "sha256": f"{i:x}" * 64} for i in range(1, 10)]}),
        changed(catalogId="Bad Id"),
        changed(cssLoaderName="a/b"),
    ],
)
def test_rejects_anything_outside_the_contract(theme: object) -> None:
    with pytest.raises(ThemeContractError):
        parse_theme_early_catalog(payload(theme))


def test_rejects_an_unsupported_schema_or_duplicate_ids() -> None:
    with pytest.raises(ThemeContractError):
        parse_theme_early_catalog(json.dumps({"schemaVersion": 2, "themes": []}).encode())
    with pytest.raises(ThemeContractError):
        parse_theme_early_catalog(payload(VALID_EARLY, VALID_EARLY))
    with pytest.raises(ThemeContractError):
        parse_theme_early_catalog(b"not json")
