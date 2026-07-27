#!/usr/bin/env python3
"""Validate the deliberately small OpenGamepadUI package contract."""

import argparse
import json
from pathlib import Path
import sys


ALLOWED_FIELDS = {
    "plugin.id",
    "plugin.name",
    "plugin.version",
    "plugin.min-api-version",
    "plugin.link",
    "plugin.source",
    "plugin.summary",
    "plugin.description",
    "entrypoint",
    "store.tags",
    "store.images",
    "author.name",
}
REQUIRED_FIELDS = ALLOWED_FIELDS
BLOCKED_FIELDS = {
    "publish",
    "release",
    "archive.url",
    "archive.sha256",
    "versions",
}
PROJECT_URL = "https://github.com/Hooandee/panel-de-control"


def read_manifest(manifest_path: Path) -> tuple[dict | None, list[str]]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, ["manifest is missing"]
    except json.JSONDecodeError as error:
        return None, [f"manifest is not valid JSON: {error.msg}"]

    if not isinstance(payload, dict):
        return None, ["manifest must be a JSON object"]
    return payload, []


def validate(manifest_path: Path, version_path: Path) -> list[str]:
    manifest, errors = read_manifest(manifest_path)
    if manifest is None:
        return errors

    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ["VERSION is missing"]

    blocked = sorted(set(manifest) & BLOCKED_FIELDS)
    for field in blocked:
        errors.append(f"unauthorized manifest field: {field}")

    unauthorized = sorted(set(manifest) - ALLOWED_FIELDS - BLOCKED_FIELDS)
    if unauthorized:
        errors.append(f"unauthorized manifest fields: {', '.join(unauthorized)}")

    missing = sorted(REQUIRED_FIELDS - set(manifest))
    if missing:
        errors.append(f"missing manifest fields: {', '.join(missing)}")

    if manifest.get("plugin.id") != "panel-de-control":
        errors.append("plugin.id must be 'panel-de-control'")
    if manifest.get("plugin.version") != version:
        errors.append("plugin.version must match VERSION")
    if manifest.get("plugin.min-api-version") != "2.0.0":
        errors.append("plugin.min-api-version must be '2.0.0'")
    if manifest.get("entrypoint") != "plugin.gd":
        errors.append("entrypoint must be 'plugin.gd'")
    if manifest.get("author.name") != "Hooandee":
        errors.append("author.name must be 'Hooandee'")

    for field in ("plugin.link", "plugin.source"):
        if manifest.get(field) != PROJECT_URL:
            errors.append(f"{field} must be '{PROJECT_URL}'")

    for field in ("plugin.name", "plugin.summary", "plugin.description"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            errors.append(f"{field} must be a non-empty string")

    tags = manifest.get("store.tags")
    if not isinstance(tags, list) or "quick-bar" not in tags:
        errors.append("store.tags must include 'quick-bar'")
    if manifest.get("store.images") != []:
        errors.append("store.images must be an empty list")

    return errors


def parse_arguments() -> argparse.Namespace:
    package_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=package_root / "plugin.json")
    parser.add_argument("--version-file", type=Path, default=package_root / "VERSION")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    errors = validate(arguments.manifest, arguments.version_file)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
