#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile


PLUGIN_ID = "panel-de-control"
PACKAGE_NAME = f"{PLUGIN_ID}.zip"
PLUGIN_ROOT = PurePosixPath("plugins") / PLUGIN_ID
MANIFEST_PATH = PLUGIN_ROOT / "plugin.json"
PRIVATE_COMPONENTS = {
    ".agents",
    ".pdc",
    ".codex",
    ".claude",
    ".notes",
    ".superpowers",
    "__pycache__",
    "scripts",
    "tests",
}
PRIVATE_FILENAMES = {"AGENTS.md"}
ALLOWED_SUPPORT_ROOTS = {
    ".godot",
    "icon.svg",
    "icudt_godot.dat",
    "project.binary",
}


def _load_json(contents: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(contents)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Invalid {label}: expected a JSON object")
    return value


def _validate_paths(names: list[str]) -> None:
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe package path: {name}")
        if any(component in PRIVATE_COMPONENTS for component in path.parts):
            raise ValueError(f"Forbidden package entry: {name}")
        if path.name in PRIVATE_FILENAMES:
            raise ValueError(f"Forbidden package entry: {name}")
        if name.endswith((".gd", ".log", ".pyc", ".tscn")):
            raise ValueError(f"Forbidden package entry: {name}")
        if path.parts[:2] == ("plugins", PLUGIN_ID):
            continue
        if path.parts and path.parts[0] in ALLOWED_SUPPORT_ROOTS:
            continue
        raise ValueError(f"Entry outside plugin package: {name}")


def _product_sources(source: Path, suffix: str) -> list[Path]:
    paths: list[Path] = []
    for path in source.rglob(f"*{suffix}"):
        relative = path.relative_to(source)
        if any(component in PRIVATE_COMPONENTS for component in relative.parts):
            continue
        paths.append(relative)
    return paths


def validate_package(package: Path, source: Path) -> str:
    if package.name != PACKAGE_NAME:
        raise ValueError(f"Package must be named {PACKAGE_NAME}")
    if not package.is_file():
        raise ValueError(f"Package not found: {package}")

    source_version = (source / "VERSION").read_text(encoding="utf-8").strip()
    source_manifest = _load_json(
        (source / "plugin.json").read_bytes(),
        "source plugin.json",
    )
    if source_manifest.get("plugin.id") != PLUGIN_ID:
        raise ValueError(f"Source plugin.id must be {PLUGIN_ID}")
    if source_manifest.get("plugin.version") != source_version:
        raise ValueError("Source plugin.json version does not match VERSION")

    try:
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
            _validate_paths(names)
            manifest_name = MANIFEST_PATH.as_posix()
            if manifest_name not in names:
                raise ValueError(f"Package manifest missing: {manifest_name}")
            package_manifest = _load_json(
                archive.read(manifest_name),
                "package plugin.json",
            )
    except zipfile.BadZipFile as error:
        raise ValueError(f"Invalid ZIP package: {error}") from error

    if package_manifest.get("plugin.id") != PLUGIN_ID:
        raise ValueError(f"Package plugin.id must be {PLUGIN_ID}")
    package_version = package_manifest.get("plugin.version")
    if package_version != source_version:
        raise ValueError(
            f"Package version {package_version!r} does not match VERSION {source_version!r}"
        )
    if package_manifest != source_manifest:
        raise ValueError("Package plugin.json does not match source plugin.json")

    entrypoint = package_manifest.get("entrypoint")
    if not isinstance(entrypoint, str) or not entrypoint.endswith(".gd"):
        raise ValueError("Package entrypoint must name a GDScript resource")
    entrypoint_path = PLUGIN_ROOT / entrypoint
    compiled_entrypoint = entrypoint_path.with_suffix(".gdc").as_posix()
    remapped_entrypoint = f"{entrypoint_path.as_posix()}.remap"
    if compiled_entrypoint not in names or remapped_entrypoint not in names:
        raise ValueError("Package is missing the compiled entrypoint and remap")
    if not any(name.endswith(".scn") for name in names):
        raise ValueError("Package is missing compiled scene resources")

    package_names = set(names)
    for script in _product_sources(source, ".gd"):
        resource = PLUGIN_ROOT / script
        compiled = resource.with_suffix(".gdc").as_posix()
        remap = f"{resource.as_posix()}.remap"
        if compiled not in package_names or remap not in package_names:
            raise ValueError(f"Package is missing compiled script: {script.as_posix()}")
    for scene in _product_sources(source, ".tscn"):
        remap = f"{(PLUGIN_ROOT / scene).as_posix()}.remap"
        if remap not in package_names:
            raise ValueError(f"Package is missing compiled scene remap: {scene.as_posix()}")
    for sidecar in _product_sources(source, ".import"):
        packaged_sidecar = (PLUGIN_ROOT / sidecar).as_posix()
        if packaged_sidecar not in package_names:
            raise ValueError(f"Package is missing imported resource: {sidecar.as_posix()}")

    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    hash_path = package.with_suffix(f"{package.suffix}.sha256")
    hash_path.write_text(f"{digest}  {package.name}\n", encoding="ascii")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an installable OpenGamepadUI plugin package."
    )
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    try:
        digest = validate_package(args.package.resolve(), args.source.resolve())
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Validated {args.package.name}: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
