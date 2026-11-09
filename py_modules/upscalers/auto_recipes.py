"""Resolve curated game dependencies before changing a managed installation."""

import hashlib
import json
from pathlib import Path

from . import ini, recipe_catalog
from .catalog import Asset


class RecipeError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def plan(recipe, installed):
    if recipe is None or not recipe.dependencies:
        return None
    selected = recipe_catalog.bundled().match(recipe.appid, "optiscaler", game_build=installed.build_id)
    if selected is None or installed.native or installed.launcher or installed.shortcut:
        raise RecipeError("recipe_unsupported")
    return selected


def unresolved(recipe, analysis: dict, selected) -> bool:
    if not recipe:
        return False
    needs = set(recipe.needs)
    if selected:
        needs.discard("luma")
    if analysis.get("inputs", {}).get("DLSS"):
        needs.discard("nvngx_dlss")
    return bool(needs & {"luma", "mod", "nvngx_dlss"})


def dependencies(selected):
    return recipe_catalog.bundled().dependency_order(selected.dependencies) if selected else ()


def assets(selected) -> list[Asset]:
    catalog = recipe_catalog.bundled()
    result = {}
    for dependency in dependencies(selected):
        if dependency.kind == "game_files":
            spec = catalog.assets[dependency.asset]
            result[spec.id] = Asset(spec.id, spec.filename, spec.sha256, spec.size, (spec.url,), archive=True)
    return list(result.values())


def sources(selected, paths: dict[str, Path]) -> dict[str, Path]:
    result = {}
    for dependency in dependencies(selected):
        if dependency.kind != "game_files":
            continue
        root = paths[dependency.asset].resolve(strict=True)
        for destination, member in dependency.files.items():
            source = root / member
            try:
                if (not source.is_file() or source.is_symlink() or
                        not source.resolve(strict=True).is_relative_to(root) or
                        any(parent.is_symlink() for parent in source.parents if parent != root and parent.is_relative_to(root))):
                    raise RecipeError("recipe_files_invalid")
            except OSError:
                raise RecipeError("recipe_files_invalid") from None
            if destination in result:
                raise RecipeError("recipe_files_invalid")
            result[destination] = source
    return result


def verbs(selected) -> tuple[str, ...]:
    return tuple(dependency.verb for dependency in dependencies(selected) if dependency.kind == "proton_dependency")


def _configured_text(text: str, changes: dict[str, str]) -> str:
    section = ""
    settings = set()
    luma_sections = 0
    for line in text.lstrip("\ufeff").splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if section == "Luma":
                luma_sections += 1
                if luma_sections > 1:
                    raise RecipeError("recipe_unsupported")
        elif "=" in line and not line.startswith((";", "#")):
            key, value = line.split("=", 1)
            dotted = section + "." + key.strip()
            if dotted.lower() == "install.basepath" and value.strip():
                raise RecipeError("recipe_unsupported")
            if dotted == "Luma.SRUserType":
                if dotted in settings:
                    raise RecipeError("recipe_unsupported")
                settings.add(dotted)
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    return bom + ini.apply(text.removeprefix("\ufeff"), changes)


def configured_sources(selected, target: Path, directory: Path) -> dict[str, Path]:
    configuration = getattr(selected, 'configuration', {}) if selected else {}
    if not configuration:
        return {}
    target, directory = Path(target), Path(directory)
    if target.is_symlink() or directory.is_symlink() or not target.is_dir() or not directory.is_dir():
        raise RecipeError("recipe_files_invalid")
    prepared = {}
    for filename, changes in configuration.items():
        if filename != "ReShade.ini" or not changes or any(
                recipe_catalog._CONFIGURATION["ReShade.ini"].get(key) != {value} for key, value in changes.items()):
            raise RecipeError("recipe_unsupported")
        source = target / filename
        if source.is_symlink():
            raise RecipeError("recipe_files_invalid")
        try:
            text = ""
            if source.exists():
                if not source.is_file() or source.stat().st_size > 1024 * 1024:
                    raise RecipeError("recipe_files_invalid")
                with source.open(encoding="utf-8", newline="") as stream:
                    text = stream.read(1024 * 1024 + 1)
                if len(text.encode("utf-8")) > 1024 * 1024:
                    raise RecipeError("recipe_files_invalid")
            prepared[filename] = _configured_text(text, changes)
        except (OSError, UnicodeError):
            raise RecipeError("recipe_files_invalid") from None
    result = {}
    for filename, text in prepared.items():
        destination = directory / filename
        if destination.exists() or destination.is_symlink():
            raise RecipeError("recipe_files_invalid")
        try:
            with destination.open("x", encoding="utf-8", newline="") as stream:
                stream.write(text)
        except OSError:
            raise RecipeError("recipe_files_invalid") from None
        result[filename] = destination
    return result


def installed_configuration(install, appid):
    if not install or not install.get("recipe_revision"):
        return {}
    if "recipe_configuration" in install:
        return dict(install["recipe_configuration"])
    selected = recipe_catalog.bundled().match(str(appid), "optiscaler", game_build=install.get("game_build"))
    if selected is None or list(selected.dependencies) != install.get("recipe_dependencies"):
        return {}
    target = Path(install.get("target", ""))
    meta = target / ".pdc-upscaler"
    manifest_path = meta / "manifest.json"
    if any(path.is_symlink() for path in (target, meta, manifest_path, meta / "backup")):
        return {}
    try:
        if manifest_path.stat().st_size > 1024 * 1024:
            return {}
        manifest = json.loads(manifest_path.read_text())
        proven = {}
        for filename, changes in selected.configuration.items():
            digest = manifest.get("files", {}).get(filename)
            if not isinstance(digest, str):
                continue
            original = ""
            if filename in manifest.get("backups", []):
                backup = meta / "backup" / filename
                if backup.is_symlink() or not backup.is_file() or backup.stat().st_size > 1024 * 1024:
                    continue
                with backup.open(encoding="utf-8", newline="") as stream:
                    original = stream.read(1024 * 1024 + 1)
                if len(original.encode("utf-8")) > 1024 * 1024:
                    continue
            expected = _configured_text(original, changes).encode("utf-8")
            if hashlib.sha256(expected).hexdigest() == digest:
                proven[filename] = dict(changes)
        return proven
    except (OSError, UnicodeError, ValueError, RecipeError):
        return {}


def restore_configuration(path: Path, backup: Path, changes: dict[str, str]):
    if path.is_symlink():
        raise RecipeError("recipe_files_invalid")
    with path.open(encoding="utf-8", newline="") as stream:
        text = stream.read(1024 * 1024 + 1)
    if len(text.encode("utf-8")) > 1024 * 1024:
        raise RecipeError("recipe_files_invalid")
    original = ""
    if backup.is_symlink():
        raise RecipeError("recipe_files_invalid")
    if backup.exists():
        with backup.open(encoding="utf-8", newline="") as stream:
            original = stream.read(1024 * 1024 + 1)
        if len(original.encode("utf-8")) > 1024 * 1024:
            raise RecipeError("recipe_files_invalid")
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    text = text.removeprefix("\ufeff")
    original = original.removeprefix("\ufeff")
    for content in (text, original):
        section = ""
        sections, keys = set(), set()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped[1:-1]
                if any(key.startswith(section + ".") for key in changes):
                    if section in sections:
                        raise RecipeError("recipe_unsupported")
                    sections.add(section)
            elif "=" in line and not stripped.startswith((";", "#")):
                dotted = section + "." + line.split("=", 1)[0].strip()
                if dotted in changes:
                    if dotted in keys:
                        raise RecipeError("recipe_unsupported")
                    keys.add(dotted)
    for dotted, applied in changes.items():
        if ini.read(text, dotted) != applied:
            continue
        previous = ini.read(original, dotted)
        if previous is not None:
            text = ini.apply(text, {dotted: previous})
            continue
        section, key = dotted.split(".", 1)
        inside = False
        lines = []
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                inside = stripped[1:-1] == section
            if inside and "=" in line and line.split("=", 1)[0].strip() == key:
                continue
            lines.append(line)
        text = "".join(lines)
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(bom + text)
