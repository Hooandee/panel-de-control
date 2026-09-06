from __future__ import annotations

import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


_SAFE_CATALOG_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STABLE_SEMVER = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PERCENT_ENCODED_DOT = re.compile(r"%2e", re.IGNORECASE)
_PERCENT_ENCODED_BACKSLASH = re.compile(r"%5c", re.IGNORECASE)
_LOCALES = frozenset({"es", "en", "it"})
_SENSITIVE_JSON_FIELDS = frozenset({"catalogId", "cssLoaderName", "url"})
_SENSITIVE_JSON_VALUE_FIELDS = frozenset({"catalogId", "url"})
_MAX_CATALOG_ENTRIES = 32
_MAX_DISPLAY_NAME_LENGTH = 80
_MAX_DESCRIPTION_LENGTH = 400
_MAX_AUTHOR_LENGTH = 80
_MAX_CSS_LOADER_NAME_LENGTH = 128
_MAX_TAGS = 8
_MAX_NOTE_LENGTH = 1_000
_MAX_METADATA_BYTES = 64 * 1024
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_SAFE_INTEGER = 9_007_199_254_740_991

_RELEASE_REQUIRED_FIELDS = frozenset(
    {
        "schemaVersion",
        "catalogId",
        "cssLoaderName",
        "version",
        "displayName",
        "description",
        "author",
        "tags",
        "artifact",
        "minimumVersions",
    }
)
_RELEASE_OPTIONAL_FIELDS = frozenset({"exclusiveGroup", "notes"})


class ThemeContractError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ThemeArtifact:
    url: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ThemeMinimumVersions:
    panel: str
    css_loader: str
    css_loader_backend: int


@dataclass(frozen=True, slots=True)
class ThemeCatalogRelease:
    schema_version: int
    catalog_id: str
    css_loader_name: str
    version: str
    display_name: Mapping[str, str]
    description: Mapping[str, str]
    author: str
    tags: tuple[str, ...]
    artifact: ThemeArtifact
    minimum_versions: ThemeMinimumVersions
    exclusive_group: str | None
    notes: Mapping[str, str]


ThemeRelease = ThemeCatalogRelease


@dataclass(frozen=True, slots=True)
class ThemeCatalog:
    schema_version: int
    themes: tuple[ThemeCatalogRelease, ...]


def _fail(message: str) -> None:
    raise ThemeContractError(message)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            _fail(f"Duplicate JSON field: {key}")
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


def _safe_id(value: object, label: str) -> str:
    if not isinstance(value, str) or _SAFE_CATALOG_ID.fullmatch(value) is None:
        _fail(f"{label} is invalid")
    return value


def _json_string_end(value: str, start: int) -> int:
    escaped = False
    for index in range(start + 1, len(value)):
        character = value[index]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            return index + 1
    return len(value)


def _reject_escaped_sensitive_strings(value: str) -> None:
    index = 0
    while index < len(value):
        if value[index] != '"':
            index += 1
            continue
        end = _json_string_end(value, index)
        if end > len(value) or value[end - 1] != '"':
            return
        raw_key = value[index:end]
        try:
            key = json.loads(raw_key)
        except json.JSONDecodeError:
            return
        cursor = end
        while cursor < len(value) and value[cursor].isspace():
            cursor += 1
        if cursor >= len(value) or value[cursor] != ":":
            index = end
            continue
        if key not in _SENSITIVE_JSON_FIELDS:
            index = end
            continue
        if "\\" in raw_key[1:-1]:
            _fail(f"Escaped {key} field is invalid")
        if key not in _SENSITIVE_JSON_VALUE_FIELDS:
            index = end
            continue
        cursor += 1
        while cursor < len(value) and value[cursor].isspace():
            cursor += 1
        if cursor < len(value) and value[cursor] == '"':
            value_end = _json_string_end(value, cursor)
            if value_end <= len(value) and "\\" in value[cursor + 1 : value_end - 1]:
                _fail(f"Escaped {key} value is invalid")
        index = end


def _decode_json(payload: bytes, label: str) -> object:
    if not isinstance(payload, bytes) or not payload or len(payload) > _MAX_METADATA_BYTES:
        _fail(f"{label} size is invalid")
    try:
        decoded = payload.decode("utf-8", errors="strict")
        _reject_escaped_sensitive_strings(decoded)
        return json.loads(decoded, object_pairs_hook=_unique_object)
    except ThemeContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ThemeContractError(f"{label} is invalid JSON") from error


def normalize_pages_base_url(value: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("Pages base URL is required")
    if "\\" in value or _PERCENT_ENCODED_BACKSLASH.search(value):
        _fail("Pages base URL path is unsafe")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ThemeContractError("Pages base URL is invalid") from error
    hostname = parsed.hostname
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        _fail("Pages base URL must be an HTTPS origin and path")
    for segment in parsed.path.split("/"):
        decoded_dots = _PERCENT_ENCODED_DOT.sub(".", segment)
        if decoded_dots in {".", ".."}:
            _fail("Pages base URL path is unsafe")
    normalized_host = hostname.lower()
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", normalized_host, path, "", ""))


def _localized(value: object, label: str, maximum: int) -> Mapping[str, str]:
    localized = _object(value, label)
    if frozenset(localized) != _LOCALES:
        _fail(f"{label} locales are invalid")
    parsed: dict[str, str] = {}
    for locale in ("es", "en", "it"):
        text = localized[locale]
        if not isinstance(text, str) or not text.strip() or len(text) > maximum:
            _fail(f"{label} {locale} is invalid")
        parsed[locale] = text
    return MappingProxyType(parsed)


def _parse_artifact(
    value: object,
    *,
    pages_base_url: str,
    catalog_id: str,
    version: str,
) -> ThemeArtifact:
    artifact = _object(value, "Release artifact")
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
    expected_url = (
        f"{pages_base_url}/themes/v1/{catalog_id}/{version}/theme.zip"
    )
    artifact_url = artifact["url"]
    if not isinstance(artifact_url, str) or artifact_url != expected_url:
        _fail("Release artifact URL is outside its registered version path")
    return ThemeArtifact(url=artifact_url, size=size, sha256=digest)


def _parse_minimum_versions(value: object) -> ThemeMinimumVersions:
    minimum = _object(value, "Minimum versions")
    _exact_fields(
        minimum,
        required=frozenset({"panel", "cssLoader", "cssLoaderBackend"}),
        label="Minimum versions",
    )
    panel_version = _stable_version(minimum["panel"], "Minimum Panel version")
    css_loader_version = _stable_version(
        minimum["cssLoader"],
        "Minimum CSS Loader version",
    )
    backend_version = minimum["cssLoaderBackend"]
    if (
        not isinstance(backend_version, int)
        or isinstance(backend_version, bool)
        or backend_version <= 0
        or backend_version > _MAX_SAFE_INTEGER
    ):
        _fail("Minimum CSS Loader backend is invalid")
    return ThemeMinimumVersions(
        panel=panel_version,
        css_loader=css_loader_version,
        css_loader_backend=backend_version,
    )


def _parse_release_value(value: object, pages_base_url: str) -> ThemeCatalogRelease:
    release = _object(value, "Release metadata")
    _exact_fields(
        release,
        required=_RELEASE_REQUIRED_FIELDS,
        optional=_RELEASE_OPTIONAL_FIELDS,
        label="Release metadata",
    )
    schema_version = release["schemaVersion"]
    if schema_version != 1 or isinstance(schema_version, bool):
        _fail("Release schema is unsupported")
    catalog_id = _safe_id(release["catalogId"], "Release catalog id")
    css_loader_name = release["cssLoaderName"]
    if (
        not isinstance(css_loader_name, str)
        or not css_loader_name.strip()
        or len(css_loader_name) > _MAX_CSS_LOADER_NAME_LENGTH
        or "/" in css_loader_name
        or "\\" in css_loader_name
    ):
        _fail("Release CSS Loader name is invalid")
    version = _stable_version(release["version"], "Published version")
    display_name = _localized(
        release["displayName"],
        "Release display name",
        _MAX_DISPLAY_NAME_LENGTH,
    )
    description = _localized(
        release["description"],
        "Release description",
        _MAX_DESCRIPTION_LENGTH,
    )
    author = release["author"]
    if (
        not isinstance(author, str)
        or not author.strip()
        or len(author) > _MAX_AUTHOR_LENGTH
    ):
        _fail("Release author is invalid")
    raw_tags = release["tags"]
    if not isinstance(raw_tags, list) or len(raw_tags) > _MAX_TAGS:
        _fail("Release tags are invalid")
    tags = tuple(_safe_id(tag, "Release tag") for tag in raw_tags)
    exclusive_group = (
        _safe_id(release["exclusiveGroup"], "Release exclusive group")
        if "exclusiveGroup" in release
        else None
    )
    notes = (
        MappingProxyType({})
        if "notes" not in release
        else _localized(release["notes"], "Release notes", _MAX_NOTE_LENGTH)
    )
    base = normalize_pages_base_url(pages_base_url)
    return ThemeCatalogRelease(
        schema_version=1,
        catalog_id=catalog_id,
        css_loader_name=css_loader_name,
        version=version,
        display_name=display_name,
        description=description,
        author=author,
        tags=tags,
        artifact=_parse_artifact(
            release["artifact"],
            pages_base_url=base,
            catalog_id=catalog_id,
            version=version,
        ),
        minimum_versions=_parse_minimum_versions(release["minimumVersions"]),
        exclusive_group=exclusive_group,
        notes=notes,
    )


def parse_theme_release(payload: bytes, pages_base_url: str) -> ThemeCatalogRelease:
    return _parse_release_value(
        _decode_json(payload, "Release metadata"),
        pages_base_url,
    )


def parse_theme_catalog(payload: bytes, pages_base_url: str) -> ThemeCatalog:
    raw = _object(_decode_json(payload, "Theme catalog"), "Theme catalog")
    _exact_fields(
        raw,
        required=frozenset({"schemaVersion", "themes"}),
        label="Theme catalog",
    )
    schema_version = raw["schemaVersion"]
    if schema_version != 1 or isinstance(schema_version, bool):
        _fail("Theme catalog schema is unsupported")
    themes_value = raw["themes"]
    if not isinstance(themes_value, list) or len(themes_value) > _MAX_CATALOG_ENTRIES:
        _fail("Theme catalog entries are invalid")
    themes = tuple(
        _parse_release_value(release, pages_base_url) for release in themes_value
    )
    catalog_ids = {release.catalog_id for release in themes}
    if len(catalog_ids) != len(themes):
        _fail("Theme catalog ids must be unique")
    return ThemeCatalog(schema_version=1, themes=themes)
