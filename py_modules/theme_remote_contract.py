from __future__ import annotations

import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


_SAFE_CATALOG_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STABLE_SEMVER = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NOTE_LOCALES = frozenset({"es", "en", "it"})
_MAX_NOTE_LENGTH = 1_000
_MAX_METADATA_BYTES = 64 * 1024
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


class ThemeContractError(Exception):
    pass


@dataclass(frozen=True)
class ThemeArtifact:
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ThemeMinimumVersions:
    panel: str
    css_loader: str
    css_loader_backend: int


@dataclass(frozen=True)
class ThemeRelease:
    schema_version: int
    catalog_id: str
    css_loader_name: str
    version: str
    artifact: ThemeArtifact
    minimum_versions: ThemeMinimumVersions
    notes: Mapping[str, str]


def _fail(message: str) -> None:
    raise ThemeContractError(message)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            _fail(f"Duplicate release field: {key}")
        value[key] = child
    return value


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    return value


def _exact_fields(
    value: dict[str, Any],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
    label: str,
) -> None:
    fields = frozenset(value)
    if not required.issubset(fields) or not fields.issubset(required | optional):
        _fail(f"{label} fields are invalid")


def _stable_version(value: object, label: str) -> str:
    if not isinstance(value, str) or _STABLE_SEMVER.fullmatch(value) is None:
        _fail(f"{label} must be a stable semantic version")
    return value


def normalize_pages_base_url(value: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("Pages base URL is required")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ThemeContractError("Pages base URL is invalid") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        _fail("Pages base URL must be an HTTPS origin and path")
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", parsed.netloc, path, "", ""))


def _parse_notes(value: object) -> Mapping[str, str]:
    if value is None:
        return MappingProxyType({})
    notes = _object(value, "Release notes")
    if not frozenset(notes).issubset(_NOTE_LOCALES):
        _fail("Release note locale is unsupported")
    parsed: dict[str, str] = {}
    for locale, note in notes.items():
        if (
            not isinstance(note, str)
            or not note.strip()
            or len(note) > _MAX_NOTE_LENGTH
        ):
            _fail(f"Release note {locale} is invalid")
        parsed[locale] = note
    return MappingProxyType(parsed)


def parse_theme_release(payload: bytes, pages_base_url: str) -> ThemeRelease:
    if not isinstance(payload, bytes) or not payload or len(payload) > _MAX_METADATA_BYTES:
        _fail("Release metadata size is invalid")
    try:
        decoded = payload.decode("utf-8", errors="strict")
        raw = json.loads(decoded, object_pairs_hook=_unique_object)
    except ThemeContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ThemeContractError("Release metadata is invalid JSON") from error

    release = _object(raw, "Release metadata")
    _exact_fields(
        release,
        required=frozenset(
            {
                "schemaVersion",
                "catalogId",
                "cssLoaderName",
                "version",
                "artifact",
                "minimumVersions",
            }
        ),
        optional=frozenset({"notes"}),
        label="Release metadata",
    )
    if release["schemaVersion"] != 1 or isinstance(release["schemaVersion"], bool):
        _fail("Release schema is unsupported")
    catalog_id = release["catalogId"]
    if not isinstance(catalog_id, str) or _SAFE_CATALOG_ID.fullmatch(catalog_id) is None:
        _fail("Release catalog id is invalid")
    css_loader_name = release["cssLoaderName"]
    if (
        not isinstance(css_loader_name, str)
        or not css_loader_name.strip()
        or len(css_loader_name) > 128
        or "/" in css_loader_name
        or "\\" in css_loader_name
    ):
        _fail("Release CSS Loader name is invalid")
    version = _stable_version(release["version"], "Published version")

    artifact = _object(release["artifact"], "Release artifact")
    _exact_fields(
        artifact,
        required=frozenset({"url", "size", "sha256"}),
        label="Release artifact",
    )
    size = artifact["size"]
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or size <= 0
        or size > _MAX_ARTIFACT_BYTES
    ):
        _fail("Release artifact size is invalid")
    digest = artifact["sha256"]
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        _fail("Release artifact digest is invalid")
    base = normalize_pages_base_url(pages_base_url)
    expected_url = f"{base}/themes/v1/{catalog_id}/{version}/gallery.zip"
    artifact_url = artifact["url"]
    if not isinstance(artifact_url, str) or artifact_url != expected_url:
        _fail("Release artifact URL is outside its registered version path")

    minimum = _object(release["minimumVersions"], "Minimum versions")
    _exact_fields(
        minimum,
        required=frozenset({"panel", "cssLoader", "cssLoaderBackend"}),
        label="Minimum versions",
    )
    panel_version = _stable_version(minimum["panel"], "Minimum Panel version")
    css_loader_version = _stable_version(
        minimum["cssLoader"], "Minimum CSS Loader version"
    )
    backend_version = minimum["cssLoaderBackend"]
    if (
        not isinstance(backend_version, int)
        or isinstance(backend_version, bool)
        or backend_version <= 0
    ):
        _fail("Minimum CSS Loader backend is invalid")

    return ThemeRelease(
        schema_version=1,
        catalog_id=catalog_id,
        css_loader_name=css_loader_name,
        version=version,
        artifact=ThemeArtifact(url=artifact_url, size=size, sha256=digest),
        minimum_versions=ThemeMinimumVersions(
            panel=panel_version,
            css_loader=css_loader_version,
            css_loader_backend=backend_version,
        ),
        notes=_parse_notes(release.get("notes")),
    )
