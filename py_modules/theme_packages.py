from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
import threading
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Iterator
from urllib.parse import quote, unquote_to_bytes

import fcntl


_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_LEGACY_SEMVER = re.compile(r"^v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_REMOTE_ALLOWED_SUFFIXES = {
    ".css",
    ".gif",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".otf",
    ".png",
    ".ttf",
    ".txt",
    ".webp",
    ".woff",
    ".woff2",
}
_REMOTE_REQUIRED_FILES = {"theme.json", "panel-theme.json"}
_REMOTE_ASSET_SUFFIXES = _REMOTE_ALLOWED_SUFFIXES - {".css", ".json", ".txt"}
_REMOTE_ASSET_SUFFIXES.discard(".js")
_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_MAX_EXTENSION_BYTES = 2 * 1024 * 1024
_MAX_RECEIPTS = 32
_MAX_FILES = 2_048
_MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
_MIN_EXTRACTION_RESERVE_BYTES = 1024 * 1024
_MAX_ARCHIVE_PATH_BYTES = 512
_MAX_COMPRESSION_RATIO = 200
_COMPRESSION_RATIO_MIN_BYTES = 1024 * 1024
_MAX_CSS_LOADER_STATE_BYTES = 1024 * 1024
_MAX_EXISTING_MANIFEST_BYTES = 1024 * 1024
_CSS_LOADER_STATE_FILES = {"config_ROOT.json", "config_USER.json"}
_TRANSACTION_PREFIX = ".panel-theme-transaction-"
_MUTATION_LOCK_NAME = ".panel-theme-install.lock"
_TRANSACTION_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_INSTALL_LOCK = threading.RLock()


class ThemePackageError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _durable_replace(source: Path, destination: Path) -> None:
    source_parent = source.parent
    destination_parent = destination.parent
    os.replace(source, destination)
    _fsync_directory(source_parent)
    if destination_parent != source_parent:
        _fsync_directory(destination_parent)


def _durable_remove_tree(path: Path) -> None:
    if not path.exists():
        return
    parent = path.parent
    shutil.rmtree(path)
    _fsync_directory(parent)


def _remove_terminal_transaction(path: Path) -> None:
    try:
        _durable_remove_tree(path)
    except OSError:
        pass


def _fsync_tree(tree: Path) -> None:
    directories: list[Path] = []
    for current, child_directories, files in os.walk(tree, topdown=True, followlinks=False):
        current_path = Path(current)
        directories.append(current_path)
        for filename in files:
            with (current_path / filename).open("rb") as stream:
                os.fsync(stream.fileno())
        for directory in child_directories:
            if (current_path / directory).is_symlink():
                raise ThemePackageError("unsafe_archive", "Installed theme tree contains a link")
    for directory in reversed(directories):
        _fsync_directory(directory)


@contextmanager
def _mutation_lock(themes_root: Path) -> Iterator[None]:
    with _INSTALL_LOCK:
        themes_root.parent.mkdir(parents=True, exist_ok=True)
        lock_path = themes_root.parent / _MUTATION_LOCK_NAME
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(lock_path, flags, 0o600)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError("Theme mutation lock is not a regular file")
        except OSError as error:
            raise ThemePackageError("install_failed", "Theme mutation lock is unavailable") from error
        acquired = False
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError as error:
                raise ThemePackageError(
                    "transaction_busy",
                    "Another theme operation is in progress",
                ) from error
            yield
        finally:
            try:
                if acquired:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _read_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise ThemePackageError(code, f"Invalid JSON: {path.name}") from error
    if not isinstance(value, dict):
        raise ThemePackageError(code, f"Expected an object: {path.name}")
    return value


def _descriptor(value: object) -> tuple[str, str, str, str, str, int]:
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise ThemePackageError("invalid_descriptor", "Unsupported theme package descriptor")
    theme_id = value.get("id")
    theme_name = value.get("cssLoaderName")
    version = value.get("version")
    artifact = value.get("artifact")
    if not isinstance(theme_id, str) or not _SAFE_ID.fullmatch(theme_id):
        raise ThemePackageError("invalid_descriptor", "Invalid theme id")
    if (
        not isinstance(theme_name, str)
        or not theme_name.strip()
        or Path(theme_name).name != theme_name
    ):
        raise ThemePackageError("invalid_descriptor", "Invalid CSS Loader theme name")
    if not isinstance(version, str) or not _SEMVER.fullmatch(version):
        raise ThemePackageError("invalid_descriptor", "Invalid theme version")
    if not isinstance(artifact, dict):
        raise ThemePackageError("invalid_descriptor", "Missing theme artifact")
    filename = artifact.get("file")
    digest = artifact.get("sha256")
    size = artifact.get("size")
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or not filename.endswith(".zip")
    ):
        raise ThemePackageError("invalid_descriptor", "Invalid theme artifact filename")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ThemePackageError("invalid_descriptor", "Invalid theme artifact hash")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ThemePackageError("invalid_descriptor", "Invalid theme artifact size")
    return theme_id, theme_name, version, filename, digest, size


def _validate_archive_member(
    info: zipfile.ZipInfo,
    theme_name: str,
) -> PurePosixPath:
    if "\\" in info.filename:
        raise ThemePackageError("unsafe_archive", "Theme archive uses an unsafe path")
    if len(info.filename.encode("utf-8")) > _MAX_ARCHIVE_PATH_BYTES:
        raise ThemePackageError("unsafe_archive", "Theme archive path is too long")
    path = PurePosixPath(info.filename)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ThemePackageError("unsafe_archive", "Theme archive uses an unsafe path")
    if path.parts[0] != theme_name:
        raise ThemePackageError("unsafe_archive", "Theme archive must have one exact root folder")
    if len(path.parts) == 2 and path.name in _CSS_LOADER_STATE_FILES:
        raise ThemePackageError("unsafe_archive", "Theme archives cannot contain CSS Loader state")
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_ISLNK(mode):
        raise ThemePackageError("unsafe_archive", "Theme archives cannot contain links")
    if info.flag_bits & 0x1:
        raise ThemePackageError("unsafe_archive", "Theme archives cannot contain encrypted files")
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise ThemePackageError("unsafe_archive", "Theme archive compression is unsupported")
    if not info.is_dir():
        file_type = stat.S_IFMT(mode)
        if file_type not in (0, stat.S_IFREG):
            raise ThemePackageError("unsafe_archive", "Theme archives cannot contain special files")
        if mode & 0o111:
            raise ThemePackageError("unsafe_archive", "Theme archives cannot contain executables")
        if path.suffix.lower() not in _REMOTE_ALLOWED_SUFFIXES:
            raise ThemePackageError("unsafe_archive", f"Unsupported theme file: {path.name}")
        if path.suffix.lower() == ".js" and (
            len(path.parts) != 2
            or path.name != "panel-extension.js"
            or info.file_size <= 0
            or info.file_size > _MAX_EXTENSION_BYTES
        ):
            raise ThemePackageError("unsafe_archive", "Theme archive contains undeclared JavaScript")
        if (
            info.file_size >= _COMPRESSION_RATIO_MIN_BYTES
            and info.file_size > max(info.compress_size, 1) * _MAX_COMPRESSION_RATIO
        ):
            raise ThemePackageError("unsafe_archive", "Theme archive compression ratio is unsafe")
    return path


def _extract_verified_archive(
    archive: Path,
    destination: Path,
    theme_name: str,
) -> Path:
    try:
        with zipfile.ZipFile(archive) as package:
            members = package.infolist()
            if not members or len(members) > _MAX_FILES:
                raise ThemePackageError("unsafe_archive", "Theme archive file count is invalid")
            total_size = sum(info.file_size for info in members)
            if total_size > _MAX_UNCOMPRESSED_BYTES:
                raise ThemePackageError("unsafe_archive", "Theme archive is too large")
            if shutil.disk_usage(destination.parent).free < (
                total_size + _MIN_EXTRACTION_RESERVE_BYTES
            ):
                raise ThemePackageError(
                    "insufficient_space",
                    "There is not enough free space to extract the theme",
                )
            seen: set[str] = set()
            validated: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for info in members:
                path = _validate_archive_member(info, theme_name)
                comparable_path = str(path).casefold()
                if comparable_path in seen:
                    raise ThemePackageError("unsafe_archive", "Theme archive contains duplicate paths")
                seen.add(comparable_path)
                validated.append((info, path))
            extracted_size = 0
            for info, path in validated:
                output = destination.joinpath(*path.parts)
                if info.is_dir():
                    output.mkdir(parents=True, exist_ok=True)
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                with package.open(info) as source, output.open("xb") as target:
                    member_size = 0
                    while block := source.read(1024 * 1024):
                        member_size += len(block)
                        extracted_size += len(block)
                        if (
                            member_size > info.file_size
                            or extracted_size > _MAX_UNCOMPRESSED_BYTES
                        ):
                            raise ThemePackageError(
                                "unsafe_archive",
                                "Theme archive expanded beyond its declared size",
                            )
                        target.write(block)
                    if member_size != info.file_size:
                        raise ThemePackageError(
                            "unsafe_archive",
                            "Theme archive file size does not match its declaration",
                        )
    except ThemePackageError:
        raise
    except (OSError, zipfile.BadZipFile) as error:
        raise ThemePackageError("invalid_archive", "Theme archive could not be read") from error
    return destination / theme_name


def _manifest_css_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or "\\" in value:
        raise ThemePackageError("unsafe_archive", "Theme manifest uses an unsafe CSS path")
    path = PurePosixPath(value)
    if (
        path.suffix.lower() != ".css"
        or path.is_absolute()
        or not path.parts
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise ThemePackageError("unsafe_archive", "Theme manifest uses an unsafe CSS path")
    return path


def _manifest_targets(value: object) -> None:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(target, str) or not target.strip() for target in value)
    ):
        raise ThemePackageError("unsafe_archive", "Theme manifest targets are invalid")


def _css_declarations(value: object) -> set[PurePosixPath]:
    if not isinstance(value, dict):
        raise ThemePackageError("unsafe_archive", "Theme CSS declarations are invalid")
    paths: set[PurePosixPath] = set()
    for css_path, targets in value.items():
        path = _manifest_css_path(css_path)
        _manifest_targets(targets)
        paths.add(path)
    return paths


def _manifest_css_paths(theme: dict[str, Any]) -> set[PurePosixPath]:
    paths = _css_declarations(theme.get("inject"))
    patches = theme.get("patches")
    if not isinstance(patches, dict):
        raise ThemePackageError("unsafe_archive", "Theme patch declarations are invalid")
    for patch_name, patch in patches.items():
        if not isinstance(patch_name, str) or not patch_name.strip() or not isinstance(patch, dict):
            raise ThemePackageError("unsafe_archive", "Theme patch declarations are invalid")
        default = patch.get("default")
        patch_type = patch.get("type")
        values = patch.get("values")
        if (
            not isinstance(default, str)
            or not isinstance(patch_type, str)
            or not patch_type.strip()
            or not isinstance(values, dict)
            or not values
            or default not in values
        ):
            raise ThemePackageError("unsafe_archive", "Theme patch declarations are invalid")
        for label, declarations in values.items():
            if not isinstance(label, str) or not label.strip():
                raise ThemePackageError("unsafe_archive", "Theme patch declarations are invalid")
            paths.update(_css_declarations(declarations))
    return paths


def _css_code_without_comments_or_strings(css: str) -> str:
    code: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(css):
        character = css[index]
        if quote is not None:
            if character in ("\n", "\r", "\f"):
                raise ThemePackageError("unsafe_archive", "Remote theme CSS is malformed")
            code.append(" ")
            if character == quote:
                quote = None
            index += 1
            continue
        if character in ('"', "'"):
            quote = character
            code.append(" ")
            index += 1
            continue
        if css.startswith("/*", index):
            comment_end = css.find("*/", index + 2)
            if comment_end < 0:
                raise ThemePackageError("unsafe_archive", "Remote theme CSS is malformed")
            code.extend(" " for _ in range(comment_end + 2 - index))
            index = comment_end + 2
            continue
        code.append(character)
        index += 1
    if quote is not None:
        raise ThemePackageError("unsafe_archive", "Remote theme CSS is malformed")
    return "".join(code)


def _quoted_css_urls(css: str, masked: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r"(?<![A-Za-z0-9_-])url\s*\(", masked, re.IGNORECASE):
        index = match.end()
        while index < len(css) and css[index].isspace():
            index += 1
        if index >= len(css) or css[index] not in ('"', "'"):
            raise ThemePackageError("unsafe_archive", "Remote theme URLs must be quoted")
        quote_character = css[index]
        end = css.find(quote_character, index + 1)
        if end < 0 or any(character in "\n\r\f" for character in css[index + 1 : end]):
            raise ThemePackageError("unsafe_archive", "Remote theme CSS is malformed")
        value = css[index + 1 : end]
        index = end + 1
        while index < len(css) and css[index].isspace():
            index += 1
        if index >= len(css) or css[index] != ")":
            raise ThemePackageError("unsafe_archive", "Remote theme URLs are malformed")
        urls.append(value)
    return urls


def _strict_unquote(value: str) -> str:
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise ThemePackageError("unsafe_archive", "Remote theme URL encoding is invalid")
    try:
        return unquote_to_bytes(value).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ThemePackageError("unsafe_archive", "Remote theme URL encoding is invalid") from error


def _resource_path(value: str, css_path: PurePosixPath, theme_name: str) -> PurePosixPath:
    if not value or any(character in value for character in ("?", "#", "\\")):
        raise ThemePackageError("unsafe_archive", "Remote theme URL is invalid")
    mount_prefix = "/themes_custom/"
    if value.startswith(mount_prefix):
        remainder = value[len(mount_prefix) :]
        encoded_name, separator, encoded_path = remainder.partition("/")
        if (
            not separator
            or encoded_name != quote(theme_name, safe="")
            or _strict_unquote(encoded_name) != theme_name
        ):
            raise ThemePackageError("unsafe_archive", "Remote theme URL targets another theme")
        decoded_path = _strict_unquote(encoded_path)
        path = PurePosixPath(decoded_path)
    else:
        if (
            value.startswith(("/", "//"))
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value)
        ):
            raise ThemePackageError("unsafe_archive", "Remote theme URL is external")
        decoded_path = _strict_unquote(value)
        relative = PurePosixPath(decoded_path)
        path = css_path.parent / relative
    if (
        path.is_absolute()
        or not path.parts
        or any(part in ("", ".", "..") for part in path.parts)
        or path.suffix.lower() not in _REMOTE_ASSET_SUFFIXES
    ):
        raise ThemePackageError("unsafe_archive", "Remote theme URL path is unsafe")
    return path


def _validate_css_resources(
    source: Path,
    css_paths: set[PurePosixPath],
    packaged_assets: set[PurePosixPath],
    theme_name: str,
) -> None:
    forbidden_function = re.compile(
        r"(?<![A-Za-z0-9_-])"
        r"(?:local|(?:-[A-Za-z0-9]+-)?(?:image(?:-set|-rect)?|cross-fade|paint|"
        r"element|canvas|named-image))\s*\(",
        re.IGNORECASE,
    )
    referenced_assets: set[PurePosixPath] = set()
    for path in css_paths:
        css_file = source.joinpath(*path.parts)
        try:
            css = css_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ThemePackageError("unsafe_archive", "Theme CSS must be valid UTF-8") from error
        if "\\" in css:
            raise ThemePackageError(
                "unsafe_archive", "Remote theme CSS cannot contain escape sequences"
            )
        if re.search(r"[A-Za-z]/\*.*?\*/[A-Za-z]", css, re.DOTALL):
            raise ThemePackageError("unsafe_archive", "Remote theme CSS is obfuscated")
        css_code = _css_code_without_comments_or_strings(css)
        if re.search(r"@import\b", css_code, re.IGNORECASE):
            raise ThemePackageError("unsafe_archive", "Remote themes cannot import CSS")
        if forbidden_function.search(css_code):
            raise ThemePackageError("unsafe_archive", "Remote theme CSS uses an active function")
        for value in _quoted_css_urls(css, css_code):
            resource = _resource_path(value, path, theme_name)
            if resource not in packaged_assets:
                raise ThemePackageError("unsafe_archive", "Remote theme asset is missing")
            referenced_assets.add(resource)
    if referenced_assets != packaged_assets:
        raise ThemePackageError("unsafe_archive", "Remote theme assets must be referenced by CSS")


def _validate_remote_content(
    source: Path,
    theme_name: str,
    theme: dict[str, Any],
) -> None:
    manifest_version = theme.get("manifest_version")
    if (
        not isinstance(manifest_version, int)
        or isinstance(manifest_version, bool)
        or not 0 < manifest_version <= _MAX_SAFE_INTEGER
    ):
        raise ThemePackageError(
            "identity_mismatch", "Remote theme manifest backend is invalid"
        )

    files = {
        PurePosixPath(path.relative_to(source).as_posix())
        for path in source.rglob("*")
        if path.is_file()
    }
    json_files = {path for path in files if path.suffix.lower() == ".json"}
    if json_files != {PurePosixPath(path) for path in _REMOTE_REQUIRED_FILES}:
        raise ThemePackageError("unsafe_archive", "Remote theme manifests are incomplete")

    declared_css = _manifest_css_paths(theme)
    packaged_css = {path for path in files if path.suffix.lower() == ".css"}
    if not packaged_css or declared_css != packaged_css:
        raise ThemePackageError(
            "unsafe_archive", "Remote theme CSS must be declared exactly by its manifest"
        )
    packaged_assets = {
        path for path in files if path.suffix.lower() in _REMOTE_ASSET_SUFFIXES
    }
    _validate_css_resources(source, packaged_css, packaged_assets, theme_name)


def _extension_receipt(
    source: Path,
    theme_id: str,
    theme_name: str,
    version: str,
    panel: dict[str, Any],
) -> dict[str, object] | None:
    if panel.get("schemaVersion") != 2 or panel.get("catalogId") != theme_id:
        raise ThemePackageError("identity_mismatch", "Theme package marker is invalid")
    extension = panel.get("extension")
    if extension is None:
        if set(panel) != {"schemaVersion", "catalogId"}:
            raise ThemePackageError("identity_mismatch", "Theme package marker is invalid")
        if (source / "panel-extension.js").exists():
            raise ThemePackageError("unsafe_archive", "Theme extension is not declared")
        return None
    if (
        set(panel) != {"schemaVersion", "catalogId", "extension"}
        or not isinstance(extension, dict)
        or set(extension) != {"abiVersion", "entrypoint", "size", "sha256"}
        or extension.get("abiVersion") != 1
        or extension.get("entrypoint") != "panel-extension.js"
        or not isinstance(extension.get("size"), int)
        or isinstance(extension.get("size"), bool)
        or not 0 < extension["size"] <= _MAX_EXTENSION_BYTES
        or not isinstance(extension.get("sha256"), str)
        or not _SHA256.fullmatch(extension["sha256"])
    ):
        raise ThemePackageError("identity_mismatch", "Theme extension declaration is invalid")
    entrypoint = source / "panel-extension.js"
    if entrypoint.is_symlink() or not entrypoint.is_file():
        raise ThemePackageError("identity_mismatch", "Theme extension entrypoint is unavailable")
    try:
        source_bytes = entrypoint.read_bytes()
        source_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ThemePackageError("identity_mismatch", "Theme extension entrypoint is invalid") from error
    if (
        len(source_bytes) != extension["size"]
        or hashlib.sha256(source_bytes).hexdigest() != extension["sha256"]
    ):
        raise ThemePackageError("identity_mismatch", "Theme extension bytes do not match the marker")
    return {
        "catalogId": theme_id,
        "cssLoaderName": theme_name,
        "version": version,
        "abiVersion": 1,
        "entrypoint": "panel-extension.js",
        "size": extension["size"],
        "sha256": extension["sha256"],
    }


def _is_legacy_preview_marker(
    source: Path,
    theme_id: str,
    theme_name: str,
    panel: dict[str, Any],
) -> bool:
    return (
        panel.get("schemaVersion") == 1
        and panel.get("catalogId") == theme_id
        and panel.get("cssLoaderName", theme_name) == theme_name
        and panel.get("executableContent") in (None, False)
        and "extension" not in panel
        and not (source / "panel-extension.js").exists()
    )


def _validate_identity(
    source: Path,
    theme_id: str,
    theme_name: str,
    version: str,
) -> dict[str, object] | None:
    theme = _read_json(source / "theme.json", "identity_mismatch")
    panel = _read_json(source / "panel-theme.json", "identity_mismatch")
    if (
        theme.get("name") != theme_name
        or theme.get("version") != version
    ):
        raise ThemePackageError("identity_mismatch", "Theme package identity does not match its descriptor")
    _validate_remote_content(source, theme_name, theme)
    return _extension_receipt(source, theme_id, theme_name, version, panel)


def _copy_css_loader_state(source_directory: int, staged: Path, filename: str) -> None:
    read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_descriptor = os.open(filename, read_flags, dir_fd=source_directory)
    except FileNotFoundError:
        return
    except OSError as error:
        raise ThemePackageError(
            "state_invalid", "Existing CSS Loader state path is unsafe"
        ) from error

    destination = staged / filename
    try:
        metadata = os.fstat(source_descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > _MAX_CSS_LOADER_STATE_BYTES
        ):
            raise ThemePackageError(
                "state_invalid", "Existing CSS Loader state is invalid"
            )
        write_flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        mode = stat.S_IMODE(metadata.st_mode) & 0o666
        try:
            destination_descriptor = os.open(destination, write_flags, mode or 0o600)
        except OSError as error:
            raise ThemePackageError(
                "state_invalid", "CSS Loader state destination is unsafe"
            ) from error
        try:
            os.fchmod(destination_descriptor, mode or 0o600)
            total = 0
            while True:
                block = os.read(
                    source_descriptor,
                    min(64 * 1024, _MAX_CSS_LOADER_STATE_BYTES - total + 1),
                )
                if not block:
                    break
                total += len(block)
                if total > _MAX_CSS_LOADER_STATE_BYTES:
                    raise ThemePackageError(
                        "state_invalid", "Existing CSS Loader state is too large"
                    )
                view = memoryview(block)
                while view:
                    written = os.write(destination_descriptor, view)
                    if written <= 0:
                        raise ThemePackageError(
                            "state_invalid", "CSS Loader state could not be copied"
                        )
                    view = view[written:]
            os.fsync(destination_descriptor)
        finally:
            os.close(destination_descriptor)
    finally:
        os.close(source_descriptor)


def _preserve_css_loader_state(installed: Path, staged: Path) -> None:
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        source_directory = os.open(installed, directory_flags)
    except FileNotFoundError:
        return
    except OSError as error:
        raise ThemePackageError(
            "state_invalid", "Existing CSS Loader theme path is unsafe"
        ) from error
    try:
        for filename in _CSS_LOADER_STATE_FILES:
            _copy_css_loader_state(source_directory, staged, filename)
    finally:
        os.close(source_directory)


def _set_tree_ownership(tree: Path, uid: int, gid: int) -> None:
    paths = [tree]
    for current, directories, files in os.walk(tree, topdown=True, followlinks=False):
        current_path = Path(current)
        paths.extend(current_path / name for name in directories)
        paths.extend(current_path / name for name in files)
    try:
        for path in paths:
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise ThemePackageError("unsafe_archive", "Installed theme tree contains a link")
            if metadata.st_uid != uid or metadata.st_gid != gid:
                os.chown(path, uid, gid, follow_symlinks=False)
    except ThemePackageError:
        raise
    except OSError as error:
        raise ThemePackageError(
            "install_failed",
            "Theme files could not be handed to CSS Loader",
        ) from error


def _read_existing_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ThemePackageError("identity_mismatch", "Existing theme identity is unsafe")
    try:
        if path.stat().st_size > _MAX_EXISTING_MANIFEST_BYTES:
            raise ThemePackageError("identity_mismatch", "Existing theme identity is too large")
    except OSError as error:
        raise ThemePackageError("identity_mismatch", "Existing theme identity is unavailable") from error
    return _read_json(path, "identity_mismatch")


def _verify_owned_destination(installed: Path, theme_id: str, theme_name: str) -> None:
    if not installed.exists():
        return
    if installed.is_symlink() or not installed.is_dir():
        raise ThemePackageError("identity_mismatch", "Existing theme path is not Panel-owned")
    panel_manifest = installed / "panel-theme.json"
    if panel_manifest.exists() or panel_manifest.is_symlink():
        theme = _read_existing_manifest(installed / "theme.json")
        panel = _read_existing_manifest(panel_manifest)
        version = theme.get("version")
        if (
            theme.get("name") != theme_name
            or not isinstance(version, str)
        ):
            raise ThemePackageError("identity_mismatch", "Existing theme marker is not Panel-owned")
        if _is_legacy_preview_marker(installed, theme_id, theme_name, panel):
            if not _LEGACY_SEMVER.fullmatch(version):
                raise ThemePackageError(
                    "identity_mismatch",
                    "Existing theme marker is not Panel-owned",
                )
            return
        if not _SEMVER.fullmatch(version):
            raise ThemePackageError("identity_mismatch", "Existing theme marker is not Panel-owned")
        _extension_receipt(installed, theme_id, theme_name, version, panel)
        return

    theme = _read_existing_manifest(installed / "theme.json")
    legacy_files = ("tokens.css", "home.css", "system.css", "settings.css", "qam.css")
    if (
        theme_id != "hooandee-gallery"
        or theme.get("name") != theme_name
        or theme.get("display_name") != theme_name
        or theme.get("author") != "Hooandee"
        or theme.get("target") != "System-Wide"
        or theme.get("manifest_version") != 9
        or not isinstance(theme.get("version"), str)
        or not re.fullmatch(r"v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", str(theme["version"]))
        or not isinstance(theme.get("inject"), dict)
        or any(
            (installed / filename).is_symlink() or not (installed / filename).is_file()
            for filename in legacy_files
        )
    ):
        raise ThemePackageError("identity_mismatch", "Existing theme is not a recognized Gallery install")


def _installed_identity(
    installed: Path,
    theme_id: str,
    theme_name: str,
) -> tuple[str, dict[str, object] | None]:
    _verify_owned_destination(installed, theme_id, theme_name)
    theme = _read_existing_manifest(installed / "theme.json")
    version = theme.get("version")
    if not isinstance(version, str) or not re.fullmatch(
        r"v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version
    ):
        raise ThemePackageError("identity_mismatch", "Existing theme version is invalid")
    panel_path = installed / "panel-theme.json"
    if not panel_path.exists():
        return version, None
    normalized = version.removeprefix("v")
    panel = _read_existing_manifest(panel_path)
    if _is_legacy_preview_marker(installed, theme_id, theme_name, panel):
        return normalized, None
    receipt = _extension_receipt(
        installed,
        theme_id,
        theme_name,
        normalized,
        panel,
    )
    return normalized, receipt


def _ensure_themes_root(root: Path) -> os.stat_result:
    if root.is_symlink():
        raise ThemePackageError("install_failed", "CSS Loader themes path is unsafe")
    if not root.exists():
        owner = root.parent.stat()
        try:
            root.mkdir(mode=0o755)
            os.chown(
                root,
                owner.st_uid,
                owner.st_gid,
                follow_symlinks=False,
            )
        except OSError as error:
            raise ThemePackageError(
                "install_failed", "CSS Loader themes path could not be created"
            ) from error
    if root.is_symlink() or not root.is_dir():
        raise ThemePackageError("install_failed", "CSS Loader themes path is unsafe")
    return root.stat()


def _validated_receipt(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict) or set(value) != {
        "catalogId",
        "cssLoaderName",
        "version",
        "abiVersion",
        "entrypoint",
        "size",
        "sha256",
    }:
        return None
    catalog_id = value.get("catalogId")
    theme_name = value.get("cssLoaderName")
    version = value.get("version")
    size = value.get("size")
    digest = value.get("sha256")
    if (
        not isinstance(catalog_id, str)
        or not _SAFE_ID.fullmatch(catalog_id)
        or not isinstance(theme_name, str)
        or not theme_name.strip()
        or Path(theme_name).name != theme_name
        or not isinstance(version, str)
        or not _SEMVER.fullmatch(version)
        or value.get("abiVersion") != 1
        or value.get("entrypoint") != "panel-extension.js"
        or not isinstance(size, int)
        or isinstance(size, bool)
        or not 0 < size <= _MAX_EXTENSION_BYTES
        or not isinstance(digest, str)
        or not _SHA256.fullmatch(digest)
    ):
        return None
    return dict(value)


def _read_receipts(path: Path, *, strict: bool) -> list[dict[str, object]]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        if strict:
            raise ThemePackageError("invalid_receipts", "Theme extension receipts are unsafe")
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        if strict:
            raise ThemePackageError("invalid_receipts", "Theme extension receipts are invalid") from error
        return []
    raw_receipts = value.get("receipts") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != {"schemaVersion", "receipts"}
        or value.get("schemaVersion") != 1
        or not isinstance(raw_receipts, list)
        or len(raw_receipts) > _MAX_RECEIPTS
    ):
        if strict:
            raise ThemePackageError("invalid_receipts", "Theme extension receipts are invalid")
        return []
    receipts: list[dict[str, object]] = []
    identities: set[str] = set()
    for raw in raw_receipts:
        receipt = _validated_receipt(raw)
        if receipt is None or str(receipt["catalogId"]) in identities:
            if strict:
                raise ThemePackageError("invalid_receipts", "Theme extension receipts are invalid")
            continue
        identities.add(str(receipt["catalogId"]))
        receipts.append(receipt)
    return receipts


def _write_receipts(path: Path, receipts: list[dict[str, object]]) -> None:
    if len(receipts) > _MAX_RECEIPTS:
        raise ThemePackageError("invalid_receipts", "Theme extension receipt limit was exceeded")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ThemePackageError("invalid_receipts", "Theme extension receipt path is unsafe")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(
                {"schemaVersion": 1, "receipts": receipts},
                stream,
                sort_keys=True,
                separators=(",", ":"),
            )
            stream.flush()
            os.fsync(stream.fileno())
        _durable_replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _replace_receipt(
    path: Path,
    catalog_id: str,
    receipt: dict[str, object] | None,
) -> None:
    receipts = _read_receipts(path, strict=True)
    updated = [item for item in receipts if item["catalogId"] != catalog_id]
    if receipt is not None:
        validated = _validated_receipt(receipt)
        if validated is None or validated["catalogId"] != catalog_id:
            raise ThemePackageError("invalid_receipts", "Theme extension receipt is invalid")
        updated.append(validated)
    updated.sort(key=lambda item: str(item["catalogId"]))
    _write_receipts(path, updated)


def _write_journal(path: Path, value: dict[str, object]) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        _durable_replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_transaction(work: Path, expected_token: str | None = None) -> dict[str, object]:
    if work.is_symlink() or not work.is_dir():
        raise ThemePackageError("invalid_transaction", "Theme transaction path is unsafe")
    journal = _read_json(work / "transaction.json", "invalid_transaction")
    token = journal.get("token")
    theme_id = journal.get("themeId")
    theme_name = journal.get("themeName")
    version = journal.get("version")
    previous_version = journal.get("previousVersion")
    new_receipt = journal.get("newReceipt")
    previous_receipt = journal.get("previousReceipt")
    state = journal.get("state")
    if (
        set(journal) != {
            "schemaVersion",
            "token",
            "themeId",
            "themeName",
            "version",
            "hadPrevious",
            "previousVersion",
            "newReceipt",
            "previousReceipt",
            "state",
        }
        or journal.get("schemaVersion") != 2
        or not isinstance(token, str)
        or not _TRANSACTION_TOKEN.fullmatch(token)
        or work.name != f"{_TRANSACTION_PREFIX}{token}"
        or (expected_token is not None and token != expected_token)
        or not isinstance(theme_id, str)
        or not _SAFE_ID.fullmatch(theme_id)
        or not isinstance(theme_name, str)
        or Path(theme_name).name != theme_name
        or not isinstance(version, str)
        or not _SEMVER.fullmatch(version)
        or not isinstance(journal.get("hadPrevious"), bool)
        or (
            previous_version is not None
            and (
                not isinstance(previous_version, str)
                or not re.fullmatch(r"v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", previous_version)
            )
        )
        or (journal["hadPrevious"] and previous_version is None)
        or (not journal["hadPrevious"] and previous_version is not None)
        or (new_receipt is not None and _validated_receipt(new_receipt) is None)
        or (state == "created" and new_receipt is not None)
        or (previous_receipt is not None and _validated_receipt(previous_receipt) is None)
        or (
            isinstance(new_receipt, dict)
            and (
                new_receipt.get("catalogId") != theme_id
                or new_receipt.get("cssLoaderName") != theme_name
                or new_receipt.get("version") != version
            )
        )
        or (
            isinstance(previous_receipt, dict)
            and (
                previous_receipt.get("catalogId") != theme_id
                or previous_receipt.get("cssLoaderName") != theme_name
                or previous_receipt.get("version") != str(previous_version).removeprefix("v")
            )
        )
        or state not in (
            "created",
            "staged",
            "swapped",
            "rolled_back",
            "acknowledged",
            "committed",
        )
    ):
        raise ThemePackageError("invalid_transaction", "Theme transaction journal is invalid")
    return journal


def _transaction_path(themes_root: Path, token: str) -> Path:
    if not _TRANSACTION_TOKEN.fullmatch(token):
        raise ThemePackageError("invalid_transaction", "Theme transaction token is invalid")
    return themes_root.parent / f"{_TRANSACTION_PREFIX}{token}"


def _authenticate_transaction(
    work: Path,
    journal: dict[str, object],
    root: Path,
) -> dict[str, str]:
    theme_id = str(journal["themeId"])
    theme_name = str(journal["themeName"])
    new_version = str(journal["version"])
    previous_version = journal["previousVersion"]
    previous_normalized = (
        str(previous_version).removeprefix("v") if previous_version is not None else None
    )
    state = journal["state"]
    destination = root / theme_name
    if state == "created":
        allowed = {"transaction.json", "extracted"}
        if any(child.name not in allowed for child in work.iterdir()):
            raise ThemePackageError("invalid_transaction", "Created transaction has unsafe files")
        extracted = work / "extracted"
        if extracted.exists() and (extracted.is_symlink() or not extracted.is_dir()):
            raise ThemePackageError("invalid_transaction", "Created transaction staging is unsafe")
        if journal["hadPrevious"]:
            if destination.is_symlink() or not destination.is_dir():
                raise ThemePackageError("invalid_transaction", "Previous theme is unavailable")
            version, receipt = _installed_identity(destination, theme_id, theme_name)
            if (
                version.removeprefix("v") != previous_normalized
                or receipt != journal["previousReceipt"]
            ):
                raise ThemePackageError("invalid_transaction", "Previous theme identity is invalid")
            return {"destination": "previous"}
        if destination.exists() or destination.is_symlink():
            raise ThemePackageError("invalid_transaction", "Created transaction destination changed")
        return {}

    identities: dict[str, str] = {}
    candidates = {
        "destination": destination,
        "previous": work / "previous",
        "rejected": work / "rejected",
        "rejected-install": work / "rejected-install",
        "extracted": work / "extracted" / theme_name,
    }
    for label, path in candidates.items():
        if not path.exists() and not path.is_symlink():
            continue
        version, receipt = _installed_identity(path, theme_id, theme_name)
        normalized = version.removeprefix("v")
        matches_new = normalized == new_version and receipt == journal["newReceipt"]
        matches_previous = (
            previous_normalized is not None
            and normalized == previous_normalized
            and receipt == journal["previousReceipt"]
        )
        if matches_new and matches_previous:
            if label == "previous" or (
                label == "destination" and candidates["rejected"].exists()
            ):
                identities[label] = "previous"
            else:
                identities[label] = "new"
        elif matches_new:
            identities[label] = "new"
        elif matches_previous:
            identities[label] = "previous"
        else:
            raise ThemePackageError(
                "invalid_transaction", "Theme transaction identity is invalid"
            )
    if not identities:
        raise ThemePackageError("invalid_transaction", "Theme transaction has no owned files")
    if state == "swapped":
        expected_topologies = (
            {"destination": "new", "previous": "previous"}
            if journal["hadPrevious"]
            else {"destination": "new"},
            {"rejected": "new", "previous": "previous"}
            if journal["hadPrevious"]
            else {"rejected": "new"},
            {"destination": "previous", "rejected": "new"}
            if journal["hadPrevious"]
            else {"rejected": "new"},
        )
        if identities not in expected_topologies:
            raise ThemePackageError("invalid_transaction", "Prepared theme identity is invalid")
    if state == "rolled_back" and (
        journal["hadPrevious"] and identities.get("destination") != "previous"
    ):
        raise ThemePackageError("invalid_transaction", "Rolled back theme identity is invalid")
    if state == "committed" and identities.get("destination") != "new":
        raise ThemePackageError("invalid_transaction", "Committed theme identity is invalid")
    return identities


def _swap_theme(source: Path, destination: Path, backup: Path) -> None:
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ThemePackageError("install_failed", "Existing theme path is unsafe")
    try:
        if destination.exists():
            _durable_replace(destination, backup)
        _durable_replace(source, destination)
    except OSError as error:
        if backup.exists():
            try:
                if destination.exists():
                    _durable_replace(destination, backup.parent / "rejected-install")
                _durable_replace(backup, destination)
            except OSError as rollback_error:
                raise ThemePackageError(
                    "rollback_failed",
                    "Theme installation failed and the previous theme could not be restored",
                ) from rollback_error
        raise ThemePackageError("install_failed", "Theme installation failed") from error


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _active_transaction(themes_root: Path) -> bool:
    for work in themes_root.parent.glob(f"{_TRANSACTION_PREFIX}*"):
        try:
            journal = _read_transaction(work)
        except ThemePackageError as error:
            raise ThemePackageError(
                "invalid_journal",
                "A theme transaction journal requires recovery",
            ) from error
        if journal["state"] not in ("acknowledged", "committed"):
            return True
        try:
            _durable_remove_tree(work)
        except OSError:
            continue
    return False


def prepare_theme_archive(
    archive: str | Path,
    descriptor: object,
    themes_root: str | Path,
    *,
    receipts_path: str | Path,
) -> dict[str, object]:
    archive_path = Path(archive)
    root = Path(themes_root)
    receipt_store = Path(receipts_path)
    theme_id, theme_name, version, _, expected_hash, expected_size = _descriptor(descriptor)
    try:
        actual_size = archive_path.stat().st_size
    except OSError as error:
        raise ThemePackageError("missing_archive", "Theme archive is unavailable") from error
    if actual_size != expected_size:
        raise ThemePackageError("size_mismatch", "Theme archive size does not match its descriptor")
    actual_hash = _hash_file(archive_path)
    if actual_hash != expected_hash:
        raise ThemePackageError("hash_mismatch", "Theme archive hash does not match its descriptor")

    with _mutation_lock(root):
        css_loader_owner = _ensure_themes_root(root)
        if _active_transaction(root):
            raise ThemePackageError("transaction_busy", "Another theme installation is pending")
        destination = root / theme_name
        _verify_owned_destination(destination, theme_id, theme_name)
        previous_version: str | None = None
        previous_receipt: dict[str, object] | None = None
        if destination.exists():
            previous_version, previous_receipt = _installed_identity(
                destination, theme_id, theme_name
            )
        persisted_receipts = _read_receipts(receipt_store, strict=True)
        persisted_previous = next(
            (item for item in persisted_receipts if item["catalogId"] == theme_id),
            None,
        )
        if persisted_previous != previous_receipt:
            raise ThemePackageError(
                "invalid_receipts", "Installed theme receipt does not match its files"
            )
        transaction_token = secrets.token_urlsafe(32)
        published_work = _transaction_path(root, transaction_token)
        while published_work.exists() or published_work.is_symlink():
            transaction_token = secrets.token_urlsafe(32)
            published_work = _transaction_path(root, transaction_token)
        work = Path(tempfile.mkdtemp(prefix=".panel-theme-building-", dir=root.parent))
        prepared = False
        retain_for_recovery = False
        try:
            created_journal = {
                "schemaVersion": 2,
                "token": transaction_token,
                "themeId": theme_id,
                "themeName": theme_name,
                "version": version,
                "hadPrevious": destination.exists(),
                "previousVersion": previous_version,
                "newReceipt": None,
                "previousReceipt": previous_receipt,
                "state": "created",
            }
            _write_journal(work / "transaction.json", created_journal)
            _durable_replace(work, published_work)
            work = published_work
            extracted = _extract_verified_archive(
                archive_path,
                work / "extracted",
                theme_name,
            )
            new_receipt = _validate_identity(extracted, theme_id, theme_name, version)
            _preserve_css_loader_state(destination, extracted)
            _set_tree_ownership(extracted, css_loader_owner.st_uid, css_loader_owner.st_gid)
            _fsync_tree(extracted)
            journal = {
                **created_journal,
                "newReceipt": new_receipt,
                "state": "staged",
            }
            _write_journal(work / "transaction.json", journal)
            _swap_theme(extracted, destination, work / "previous")
            prepared = True
            _write_journal(work / "transaction.json", {**journal, "state": "swapped"})
            return {
                "ok": True,
                "code": "prepared",
                "theme_id": theme_id,
                "theme_name": theme_name,
                "version": version,
                "transaction": transaction_token,
            }
        except ThemePackageError as error:
            retain_for_recovery = error.code == "rollback_failed"
            raise
        finally:
            if not prepared and not retain_for_recovery:
                try:
                    _durable_remove_tree(work)
                except OSError:
                    pass


def _finish_rollback(
    work: Path,
    journal: dict[str, object],
    themes_root: Path,
    receipts_path: Path,
) -> None:
    _authenticate_pending_receipt(receipts_path, journal)
    destination = themes_root / str(journal["themeName"])
    backup = work / "previous"
    rejected = work / "rejected"
    identities = _authenticate_transaction(work, journal, themes_root)
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ThemePackageError("rollback_failed", "Installed theme path is unsafe")
    try:
        if identities.get("destination") == "new":
            _durable_replace(destination, rejected)
            identities = {
                **{key: value for key, value in identities.items() if key != "destination"},
                "rejected": "new",
            }
        elif identities.get("rejected") != "new":
            raise OSError("Rejected theme is unavailable")
        if journal["hadPrevious"]:
            if identities.get("previous") == "previous":
                if backup.is_symlink() or not backup.is_dir() or destination.exists():
                    raise OSError("Previous theme backup is unavailable")
                _durable_replace(backup, destination)
            elif identities.get("destination") != "previous":
                raise OSError("Previous theme backup is unavailable")
        elif destination.exists() or destination.is_symlink():
            raise OSError("New theme destination was not removed")
    except OSError as error:
        if rejected.exists() and not destination.exists() and backup.exists():
            try:
                _durable_replace(rejected, destination)
            except OSError:
                pass
        raise ThemePackageError(
            "rollback_failed",
            "The previous theme could not be restored",
        ) from error
    _replace_receipt(
        receipts_path,
        str(journal["themeId"]),
        journal["previousReceipt"] if isinstance(journal["previousReceipt"], dict) else None,
    )
    _write_journal(work / "transaction.json", {**journal, "state": "rolled_back"})


def _current_receipt(
    receipts_path: Path,
    catalog_id: str,
) -> dict[str, object] | None:
    return next(
        (
            receipt
            for receipt in _read_receipts(receipts_path, strict=True)
            if receipt["catalogId"] == catalog_id
        ),
        None,
    )


def _authenticate_pending_receipt(
    receipts_path: Path,
    journal: dict[str, object],
) -> None:
    current = _current_receipt(receipts_path, str(journal["themeId"]))
    previous = journal["previousReceipt"]
    new = journal["newReceipt"]
    if current != previous and current != new:
        raise ThemePackageError(
            "invalid_transaction",
            "Theme transaction receipt identity is invalid",
        )


def _installed_version(destination: Path) -> str | None:
    try:
        theme = _read_json(destination / "theme.json", "invalid_transaction")
    except ThemePackageError:
        return None
    version = theme.get("version")
    return version if isinstance(version, str) else None


def _pending_recovery(work: Path, journal: dict[str, object], root: Path) -> dict[str, object]:
    return {
        "transaction": journal["token"],
        "theme_name": journal["themeName"],
        "previous_version": _installed_version(root / str(journal["themeName"])),
    }


def commit_theme_install(
    token: str,
    themes_root: str | Path,
    *,
    receipts_path: str | Path,
) -> dict[str, object]:
    root = Path(themes_root)
    receipt_store = Path(receipts_path)
    with _mutation_lock(root):
        work = _transaction_path(root, token)
        journal = _read_transaction(work, token)
        if journal["state"] != "swapped":
            raise ThemePackageError("invalid_transaction", "Theme transaction is already complete")
        _authenticate_transaction(work, journal, root)
        _replace_receipt(
            receipt_store,
            str(journal["themeId"]),
            journal["newReceipt"] if isinstance(journal["newReceipt"], dict) else None,
        )
        _write_journal(work / "transaction.json", {**journal, "state": "committed"})
        _remove_terminal_transaction(work)
        return {"ok": True, "code": "committed"}


def rollback_theme_install(
    token: str,
    themes_root: str | Path,
    *,
    receipts_path: str | Path,
) -> dict[str, object]:
    root = Path(themes_root)
    receipt_store = Path(receipts_path)
    with _mutation_lock(root):
        work = _transaction_path(root, token)
        journal = _read_transaction(work, token)
        if journal["state"] != "swapped":
            raise ThemePackageError("invalid_transaction", "Theme transaction is already complete")
        _authenticate_transaction(work, journal, root)
        _finish_rollback(work, journal, root, receipt_store)
        return {"ok": True, "code": "rolled_back"}


def acknowledge_theme_rollback(
    token: str,
    themes_root: str | Path,
    *,
    receipts_path: str | Path,
) -> dict[str, object]:
    root = Path(themes_root)
    with _mutation_lock(root):
        work = _transaction_path(root, token)
        journal = _read_transaction(work, token)
        if journal["state"] != "rolled_back":
            raise ThemePackageError("invalid_transaction", "Theme rollback is not ready to acknowledge")
        _authenticate_transaction(work, journal, root)
        _write_journal(work / "transaction.json", {**journal, "state": "acknowledged"})
        _remove_terminal_transaction(work)
        return {"ok": True, "code": "acknowledged"}


def _recover_transaction(
    work: Path,
    journal: dict[str, object],
    root: Path,
    receipts_path: Path,
) -> bool:
    _authenticate_transaction(work, journal, root)
    state = journal["state"]
    if state in ("acknowledged", "committed"):
        _remove_terminal_transaction(work)
        return False
    if state == "created":
        previous_receipt = (
            journal["previousReceipt"]
            if isinstance(journal["previousReceipt"], dict)
            else None
        )
        if _current_receipt(receipts_path, str(journal["themeId"])) != previous_receipt:
            raise ThemePackageError(
                "invalid_transaction",
                "Created transaction receipt identity is invalid",
            )
        _durable_remove_tree(work)
        return False
    if state == "swapped":
        _authenticate_pending_receipt(receipts_path, journal)
    if state == "rolled_back":
        _replace_receipt(
            receipts_path,
            str(journal["themeId"]),
            journal["previousReceipt"] if isinstance(journal["previousReceipt"], dict) else None,
        )
        return True

    destination = root / str(journal["themeName"])
    backup = work / "previous"
    rejected = work / "rejected"
    installed_version = _installed_version(destination) if destination.exists() else None
    new_version = journal["version"]

    if state == "staged" and journal["hadPrevious"] and not backup.exists():
        if destination.exists() and installed_version != new_version and not rejected.exists():
            _durable_remove_tree(work)
            return False
        _replace_receipt(
            receipts_path,
            str(journal["themeId"]),
            journal["previousReceipt"] if isinstance(journal["previousReceipt"], dict) else None,
        )
        _write_journal(work / "transaction.json", {**journal, "state": "rolled_back"})
        return True
    if state == "staged" and not journal["hadPrevious"] and not destination.exists():
        if (work / "extracted").exists():
            _durable_remove_tree(work)
            return False
        _replace_receipt(receipts_path, str(journal["themeId"]), None)
        _write_journal(work / "transaction.json", {**journal, "state": "rolled_back"})
        return True
    if journal["hadPrevious"] and not destination.exists() and backup.exists():
        _durable_replace(backup, destination)
        if state == "staged" and (work / "extracted").exists():
            _durable_remove_tree(work)
            return False
        _replace_receipt(
            receipts_path,
            str(journal["themeId"]),
            journal["previousReceipt"] if isinstance(journal["previousReceipt"], dict) else None,
        )
        _write_journal(work / "transaction.json", {**journal, "state": "rolled_back"})
        return True
    if journal["hadPrevious"] and not backup.exists() and destination.exists() and installed_version != new_version:
        _replace_receipt(
            receipts_path,
            str(journal["themeId"]),
            journal["previousReceipt"] if isinstance(journal["previousReceipt"], dict) else None,
        )
        _write_journal(work / "transaction.json", {**journal, "state": "rolled_back"})
        return True

    _finish_rollback(work, journal, root, receipts_path)
    return True


def recover_theme_transactions(
    themes_root: str | Path,
    *,
    receipts_path: str | Path,
) -> list[dict[str, object]]:
    root = Path(themes_root)
    receipt_store = Path(receipts_path)
    pending: list[dict[str, object]] = []
    with _mutation_lock(root):
        if not root.parent.exists():
            return []
        for work in sorted(root.parent.glob(f"{_TRANSACTION_PREFIX}*")):
            try:
                journal = _read_transaction(work)
            except ThemePackageError as error:
                raise ThemePackageError(
                    "invalid_journal",
                    "A theme transaction journal requires recovery",
                ) from error
            try:
                requires_acknowledgement = _recover_transaction(
                    work,
                    journal,
                    root,
                    receipt_store,
                )
            except ThemePackageError as error:
                if error.code not in ("identity_mismatch", "invalid_transaction"):
                    raise
                raise ThemePackageError(
                    "invalid_journal",
                    "A theme transaction journal requires recovery",
                ) from error
            if requires_acknowledgement:
                try:
                    current = _read_transaction(work)
                except ThemePackageError as error:
                    raise ThemePackageError(
                        "invalid_journal",
                        "A theme transaction journal requires recovery",
                    ) from error
                pending.append(_pending_recovery(work, current, root))
    return pending


def list_theme_extensions(
    themes_root: str | Path,
    receipts_path: str | Path,
) -> list[dict[str, object]]:
    root = Path(themes_root)
    available: list[dict[str, object]] = []
    for receipt in _read_receipts(Path(receipts_path), strict=False):
        try:
            version, installed_receipt = _installed_identity(
                root / str(receipt["cssLoaderName"]),
                str(receipt["catalogId"]),
                str(receipt["cssLoaderName"]),
            )
            if version.removeprefix("v") != receipt["version"] or installed_receipt != receipt:
                continue
        except ThemePackageError:
            continue
        available.append(dict(receipt))
    return available


def load_theme_extension(
    catalog_id: str,
    version: str,
    themes_root: str | Path,
    receipts_path: str | Path,
) -> dict[str, object]:
    if (
        not isinstance(catalog_id, str)
        or not _SAFE_ID.fullmatch(catalog_id)
        or not isinstance(version, str)
        or not _SEMVER.fullmatch(version)
    ):
        raise ThemePackageError("extension_unavailable", "Theme extension identity is invalid")
    receipt = next(
        (
            item
            for item in _read_receipts(Path(receipts_path), strict=False)
            if item["catalogId"] == catalog_id and item["version"] == version
        ),
        None,
    )
    if receipt is None:
        raise ThemePackageError("extension_unavailable", "Theme extension receipt is unavailable")
    installed = Path(themes_root) / str(receipt["cssLoaderName"])
    try:
        installed_version, installed_receipt = _installed_identity(
            installed,
            catalog_id,
            str(receipt["cssLoaderName"]),
        )
        if installed_version.removeprefix("v") != version or installed_receipt != receipt:
            raise ThemePackageError("extension_unavailable", "Theme extension identity changed")
        entrypoint = installed / str(receipt["entrypoint"])
        source_bytes = entrypoint.read_bytes()
        source = source_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError, ThemePackageError) as error:
        if isinstance(error, ThemePackageError) and error.code == "extension_unavailable":
            raise
        raise ThemePackageError(
            "extension_unavailable", "Theme extension is unavailable"
        ) from error
    if (
        len(source_bytes) != receipt["size"]
        or hashlib.sha256(source_bytes).hexdigest() != receipt["sha256"]
    ):
        raise ThemePackageError("extension_unavailable", "Theme extension bytes changed")
    return {
        "catalogId": catalog_id,
        "cssLoaderName": receipt["cssLoaderName"],
        "version": version,
        "abiVersion": receipt["abiVersion"],
        "sha256": receipt["sha256"],
        "source": source,
    }
