"""Bounded, reversible image controls for recognized OptiScaler INI layouts."""

import configparser
import math
import os
import stat
import uuid
from pathlib import Path

from . import ini

LIMIT = 256 * 1024
SHARPNESS_KEYS = ("CAS.Enabled", "Sharpness.OverrideSharpness", "Sharpness.Sharpness")
MANAGED_SHARPNESS_KEYS = (*SHARPNESS_KEYS, "CAS.MotionSharpnessEnabled")
KEYS = (*MANAGED_SHARPNESS_KEYS, "HelixSR.Int8")


class SettingsError(Exception):
    pass


def _parent(path: Path, root: Path) -> int:
    try:
        relative = path.relative_to(root)
        if not relative.parts or ".." in relative.parts:
            raise SettingsError("unsafe_path")
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in relative.parts[:-1]:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            return fd
        except Exception:
            os.close(fd)
            raise
    except (ValueError, OSError):
        raise SettingsError("unsafe_path") from None


def _read_at(parent: int, name: str) -> str:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise SettingsError("unsafe_path")
            data = handle.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise SettingsError("invalid_config")
        return data.decode("utf-8")
    except UnicodeError:
        raise SettingsError("invalid_config") from None
    except OSError:
        raise SettingsError("unsafe_path") from None


def read(path: Path, root: Path) -> str:
    parent = _parent(path, root)
    try:
        return _read_at(parent, path.name)
    finally:
        os.close(parent)


def values(text: str) -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    try:
        parser.read_string(text)
    except configparser.Error:
        raise SettingsError("invalid_config") from None
    seen = set()
    result = {}
    for section in parser.sections():
        for key, value in parser.items(section):
            dotted = f"{section}.{key}"
            if dotted.lower() in seen:
                raise SettingsError("invalid_config")
            seen.add(dotted.lower())
            if dotted in KEYS:
                result[dotted] = value.strip()
    return result


def state(text: str, helix: bool, managed: bool) -> dict:
    settings = values(text)
    sharpness = None
    if all(key in settings for key in SHARPNESS_KEYS):
        enabled, override = settings[SHARPNESS_KEYS[0]], settings[SHARPNESS_KEYS[1]]
        if enabled not in ("true", "false", "auto") or override not in ("true", "false", "auto"):
            raise SettingsError("invalid_config")
        number = settings[SHARPNESS_KEYS[2]]
        try:
            number = None if number == "auto" else float(number)
        except ValueError:
            raise SettingsError("invalid_config") from None
        if number is not None and (not math.isfinite(number) or not 0 <= number <= 1):
            raise SettingsError("invalid_config")
        motion = settings.get("CAS.MotionSharpnessEnabled", "auto")
        if motion not in ("true", "false", "auto"):
            raise SettingsError("invalid_config")
        active = None
        if override == "true" and number is not None:
            if number == 0 and motion != "true":
                active = False
            elif number > 0 and enabled == "true":
                active = True
        sharpness = {"enabled": active, "value": number}
    int8 = settings.get("HelixSR.Int8") if helix else None
    if int8 is not None and int8 not in ("auto", "on", "off"):
        raise SettingsError("invalid_config")
    supported = sharpness is not None or int8 is not None
    return {"supported": supported, "sharpness": sharpness, "int8": int8, "managed": managed,
            **({} if supported else {"reason": "unsupported_layout"})}


def changes(request: dict, current: dict, text: str) -> dict[str, str]:
    if not isinstance(request, dict) or not request or set(request) - {"sharpness", "int8"}:
        raise SettingsError("image_settings_value")
    result = {}
    if "sharpness" in request:
        value = request["sharpness"]
        if current["sharpness"] is None or not isinstance(value, dict) or set(value) != {"enabled", "value"}:
            raise SettingsError("image_settings_value")
        enabled, number = value["enabled"], value["value"]
        if type(enabled) is not bool or type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 1:
            raise SettingsError("image_settings_value")
        result = {"CAS.Enabled": "true" if enabled else "false", "Sharpness.OverrideSharpness": "true",
                  "Sharpness.Sharpness": f"{number:.2f}" if enabled else "0.00"}
        if not enabled and "CAS.MotionSharpnessEnabled" in values(text):
            result["CAS.MotionSharpnessEnabled"] = "false"
    if "int8" in request:
        if current["int8"] is None or request["int8"] not in ("auto", "on", "off"):
            raise SettingsError("image_settings_value")
        result["HelixSR.Int8"] = request["int8"]
    return result


def write(path: Path, root: Path, before: str, after: str) -> None:
    parent = _parent(path, root)
    temp = f".pdc-image-{uuid.uuid4().hex}.tmp"
    try:
        if _read_at(parent, path.name) != before:
            raise SettingsError("image_settings_changed")
        original = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, stat.S_IMODE(original.st_mode), dir_fd=parent)
        with os.fdopen(fd, "wb") as handle:
            if os.geteuid() == 0:
                os.fchown(handle.fileno(), original.st_uid, original.st_gid)
            handle.write(after.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        if _read_at(parent, path.name) != before:
            raise SettingsError("image_settings_changed")
        os.replace(temp, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
        if _read_at(parent, path.name) != after:
            raise SettingsError("image_settings_changed")
    finally:
        try:
            os.unlink(temp, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def restored(text: str, receipt: dict) -> str:
    current = values(text)
    changes = {key: value for key, value in receipt.get("original", {}).items()
               if key in KEYS and current.get(key) == receipt.get("applied", {}).get(key)}
    return ini.apply(text, changes)
