import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence


DEVICE_KEY = "rog_xbox_ally_x"
MANAGER = "inputplumber"
MANIFEST_PATH = "assets/inputplumber/compatibility.json"
_ROOT_FIELDS = {"schema", "device", "builds"}
_BUILD_FIELDS = {
    "version",
    "upstream_commit",
    "patch",
    "artifact",
    "artifact_sha256",
    "provenance",
    "stock_sha256",
    "verified_platforms",
}
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PLATFORM = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class InputPlumberBuild:
    version: str
    upstream_commit: str
    patch: str
    artifact: str
    artifact_sha256: str
    provenance: str
    stock_sha256: tuple[str, ...]
    verified_platforms: tuple[str, ...]


def _safe_relative_path(plugin_dir: str, value) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError("manifest path must be a non-empty string")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ManifestError(f"unsafe manifest path: {value}")
    root = Path(plugin_dir).resolve()
    resolved = (root / Path(*relative.parts)).resolve()
    if not resolved.is_relative_to(root):
        raise ManifestError(f"manifest path escapes plugin root: {value}")
    return relative.as_posix()


def _string_tuple(values, pattern, field) -> tuple[str, ...]:
    if not isinstance(values, list) or not values:
        raise ManifestError(f"{field} must be a non-empty list")
    if any(not isinstance(value, str) or pattern.fullmatch(value) is None for value in values):
        raise ManifestError(f"invalid {field}")
    if len(values) != len(set(values)):
        raise ManifestError(f"duplicate {field}")
    return tuple(values)


def _parse_build(plugin_dir: str, raw) -> InputPlumberBuild:
    if not isinstance(raw, dict) or set(raw) != _BUILD_FIELDS:
        raise ManifestError("invalid build fields")
    version = raw["version"]
    commit = raw["upstream_commit"]
    if not isinstance(version, str) or _VERSION.fullmatch(version) is None:
        raise ManifestError("invalid version")
    if not isinstance(commit, str) or _COMMIT.fullmatch(commit) is None:
        raise ManifestError("invalid upstream commit")
    patch = _safe_relative_path(plugin_dir, raw["patch"])
    artifact = _safe_relative_path(plugin_dir, raw["artifact"])
    artifact_sha256 = _safe_relative_path(
        plugin_dir, raw["artifact_sha256"]
    )
    provenance = _safe_relative_path(plugin_dir, raw["provenance"])
    expected_artifact = f"bin/inputplumber-xbox-hd-v{version}"
    if (
        patch != f"assets/inputplumber/v{version}-xbox-hd.patch"
        or artifact != expected_artifact
        or artifact_sha256 != f"{expected_artifact}.sha256"
        or provenance != f"{expected_artifact}.provenance"
    ):
        raise ManifestError("build paths do not match version")
    return InputPlumberBuild(
        version=version,
        upstream_commit=commit,
        patch=patch,
        artifact=artifact,
        artifact_sha256=artifact_sha256,
        provenance=provenance,
        stock_sha256=_string_tuple(
            raw["stock_sha256"], _SHA256, "stock_sha256"
        ),
        verified_platforms=_string_tuple(
            raw["verified_platforms"], _PLATFORM, "verified_platforms"
        ),
    )


def load_builds(plugin_dir: str) -> Sequence[InputPlumberBuild]:
    path = Path(plugin_dir) / MANIFEST_PATH
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError("unable to read compatibility manifest") from error
    if not isinstance(raw, dict) or set(raw) != _ROOT_FIELDS:
        raise ManifestError("invalid manifest fields")
    if raw["schema"] != 1 or raw["device"] != DEVICE_KEY:
        raise ManifestError("unsupported compatibility manifest")
    builds_raw = raw["builds"]
    if not isinstance(builds_raw, list) or not 1 <= len(builds_raw) <= 3:
        raise ManifestError("manifest must declare between one and three builds")
    builds = tuple(_parse_build(plugin_dir, build) for build in builds_raw)
    versions = [build.version for build in builds]
    if len(versions) != len(set(versions)):
        raise ManifestError("duplicate InputPlumber version")
    paths = [
        path
        for build in builds
        for path in (
            build.patch,
            build.artifact,
            build.artifact_sha256,
            build.provenance,
        )
    ]
    if len(paths) != len(set(paths)):
        raise ManifestError("duplicate InputPlumber build path")
    return tuple(
        sorted(
            builds,
            key=lambda build: tuple(int(part) for part in build.version.split(".")),
            reverse=True,
        )
    )


def select_build(
    builds: Sequence[InputPlumberBuild],
    *,
    manager: str,
    device_key: str,
    version: str | None,
    stock_sha256: str | None,
) -> InputPlumberBuild | None:
    if manager != MANAGER or device_key != DEVICE_KEY:
        return None
    for build in builds:
        if build.version == version and stock_sha256 in build.stock_sha256:
            return build
    return None


def owned_paths(
    plugin_dir: str, builds: Sequence[InputPlumberBuild]
) -> Sequence[str]:
    root = Path(plugin_dir)
    return tuple(
        str(root / relative)
        for build in builds
        for relative in (
            build.patch,
            build.artifact,
            build.artifact_sha256,
            build.provenance,
        )
    )
