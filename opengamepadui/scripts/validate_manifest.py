#!/usr/bin/env python3
"""Validate the deliberately small OpenGamepadUI package contract."""

import argparse
import json
from pathlib import Path
import sys


ALLOWED_FIELDS = {
    "id",
    "name",
    "version",
    "minimum_api_version",
    "tags",
    "description",
    "license",
}
REQUIRED_FIELDS = ALLOWED_FIELDS


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

    unauthorized = sorted(set(manifest) - ALLOWED_FIELDS)
    if unauthorized:
        errors.append(f"unauthorized manifest fields: {', '.join(unauthorized)}")

    missing = sorted(REQUIRED_FIELDS - set(manifest))
    if missing:
        errors.append(f"missing manifest fields: {', '.join(missing)}")

    if manifest.get("id") != "panel-de-control":
        errors.append("id must be 'panel-de-control'")
    if manifest.get("version") != version:
        errors.append("version must match VERSION")
    if manifest.get("minimum_api_version") != "2.0.0":
        errors.append("minimum_api_version must be '2.0.0'")

    tags = manifest.get("tags")
    if not isinstance(tags, list) or "quick-bar" not in tags:
        errors.append("tags must include 'quick-bar'")

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
