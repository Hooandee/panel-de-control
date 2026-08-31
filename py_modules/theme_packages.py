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
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

import fcntl


@dataclass(frozen=True)
class BundledTheme:
    descriptor_name: str
    css_loader_name: str
    runtime: dict[str, object]


_BUNDLED_THEMES = {
    "hooandee-gallery": BundledTheme(
        "gallery.json",
        "Hooandee Gallery",
        {
            "moduleId": "gallery",
            "surfaces": ["library", "library-grid", "game-details", "settings"],
        },
    ),
}
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ALLOWED_SUFFIXES = {
    ".css",
    ".gif",
    ".jpeg",
    ".jpg",
    ".json",
    ".md",
    ".otf",
    ".png",
    ".svg",
    ".ttf",
    ".txt",
    ".webp",
    ".woff",
    ".woff2",
}
_REMOTE_ALLOWED_SUFFIXES = {".css", ".json"}
_REMOTE_REQUIRED_FILES = {"theme.json", "panel-theme.json"}
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


class PackageProfile(Enum):
    BUNDLED_COMPAT = "bundled-compat"
    REMOTE_V1 = "remote-v1"


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
    profile: PackageProfile,
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
        allowed_suffixes = (
            _REMOTE_ALLOWED_SUFFIXES if profile is PackageProfile.REMOTE_V1 else _ALLOWED_SUFFIXES
        )
        if path.suffix.lower() not in allowed_suffixes:
            raise ThemePackageError("unsafe_archive", f"Unsupported theme file: {path.name}")
        if (
            profile is PackageProfile.REMOTE_V1
            and info.file_size >= _COMPRESSION_RATIO_MIN_BYTES
            and info.file_size > max(info.compress_size, 1) * _MAX_COMPRESSION_RATIO
        ):
            raise ThemePackageError("unsafe_archive", "Theme archive compression ratio is unsafe")
    return path


def _extract_verified_archive(
    archive: Path,
    destination: Path,
    theme_name: str,
    profile: PackageProfile,
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
                path = _validate_archive_member(info, theme_name, profile)
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


def _manifest_css_paths(value: object) -> set[PurePosixPath]:
    paths: set[PurePosixPath] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key.lower().endswith(".css"):
                if "\\" in key:
                    raise ThemePackageError("unsafe_archive", "Theme manifest uses an unsafe CSS path")
                path = PurePosixPath(key)
                if (
                    path.is_absolute()
                    or not path.parts
                    or any(part in ("", ".", "..") for part in path.parts)
                ):
                    raise ThemePackageError(
                        "unsafe_archive", "Theme manifest uses an unsafe CSS path"
                    )
                paths.add(path)
            paths.update(_manifest_css_paths(child))
    elif isinstance(value, list):
        for child in value:
            paths.update(_manifest_css_paths(child))
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
            index = comment_end + 2
            continue
        code.append(character)
        index += 1
    if quote is not None:
        raise ThemePackageError("unsafe_archive", "Remote theme CSS is malformed")
    return "".join(code)


def _validate_css_resources(source: Path, css_paths: set[PurePosixPath]) -> None:
    resource_function = re.compile(
        r"(?<![A-Za-z0-9_-])"
        r"(?:url|src|local|(?:-[A-Za-z0-9]+-)?(?:image(?:-set|-rect)?|"
        r"cross-fade|paint|element|canvas|named-image))\s*\(",
        re.IGNORECASE,
    )
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
        css_code = _css_code_without_comments_or_strings(css)
        if re.search(r"@import\b", css_code, re.IGNORECASE):
            raise ThemePackageError("unsafe_archive", "Remote themes cannot import CSS")
        if resource_function.search(css_code):
            raise ThemePackageError(
                "unsafe_archive", "Remote theme CSS cannot load resources"
            )


def _validate_remote_content(
    source: Path,
    theme_id: str,
    theme: dict[str, Any],
    panel: dict[str, Any],
) -> None:
    registered = _BUNDLED_THEMES[theme_id]
    if panel.get("runtime") != registered.runtime or theme.get("manifest_version") != 9:
        raise ThemePackageError(
            "identity_mismatch", "Remote theme runtime is not compiled into Panel de Control"
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
    _validate_css_resources(source, packaged_css)


def _validate_identity(
    source: Path,
    theme_id: str,
    theme_name: str,
    version: str,
    profile: PackageProfile,
) -> None:
    theme = _read_json(source / "theme.json", "identity_mismatch")
    panel = _read_json(source / "panel-theme.json", "identity_mismatch")
    if (
        theme.get("name") != theme_name
        or theme.get("version") != version
        or panel.get("schemaVersion") != 1
        or panel.get("catalogId") != theme_id
    ):
        raise ThemePackageError("identity_mismatch", "Theme package identity does not match its descriptor")
    if profile is PackageProfile.REMOTE_V1:
        _validate_remote_content(source, theme_id, theme, panel)


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
        panel = _read_existing_manifest(panel_manifest)
        if panel.get("schemaVersion") != 1 or panel.get("catalogId") != theme_id:
            raise ThemePackageError("identity_mismatch", "Existing theme marker is not Panel-owned")
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
    state = journal.get("state")
    if (
        journal.get("schemaVersion") != 1
        or not isinstance(token, str)
        or not _TRANSACTION_TOKEN.fullmatch(token)
        or (expected_token is not None and token != expected_token)
        or not isinstance(theme_id, str)
        or not _SAFE_ID.fullmatch(theme_id)
        or not isinstance(theme_name, str)
        or Path(theme_name).name != theme_name
        or not isinstance(version, str)
        or not _SEMVER.fullmatch(version)
        or not isinstance(journal.get("hadPrevious"), bool)
        or theme_id not in _BUNDLED_THEMES
        or _BUNDLED_THEMES[theme_id].css_loader_name != theme_name
        or state not in ("staged", "swapped", "rolled_back", "acknowledged", "committed")
    ):
        raise ThemePackageError("invalid_transaction", "Theme transaction journal is invalid")
    return journal


def _transaction_path(themes_root: Path, token: str) -> Path:
    if not _TRANSACTION_TOKEN.fullmatch(token):
        raise ThemePackageError("invalid_transaction", "Theme transaction token is invalid")
    return themes_root.parent / f"{_TRANSACTION_PREFIX}{token}"


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
    profile: PackageProfile = PackageProfile.BUNDLED_COMPAT,
) -> dict[str, object]:
    archive_path = Path(archive)
    root = Path(themes_root)
    theme_id, theme_name, version, _, expected_hash, expected_size = _descriptor(descriptor)
    registered = _BUNDLED_THEMES.get(theme_id)
    if registered is None or registered.css_loader_name != theme_name:
        raise ThemePackageError(
            "identity_mismatch", "Theme package does not target a Panel-owned CSS Loader theme"
        )
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
        token = secrets.token_urlsafe(32)
        work = Path(tempfile.mkdtemp(prefix=f"{_TRANSACTION_PREFIX}{token}-", dir=root.parent))
        _fsync_directory(root.parent)
        transaction_token = work.name.removeprefix(_TRANSACTION_PREFIX)
        prepared = False
        retain_for_recovery = False
        try:
            extracted = _extract_verified_archive(
                archive_path,
                work / "extracted",
                theme_name,
                profile,
            )
            _validate_identity(extracted, theme_id, theme_name, version, profile)
            _preserve_css_loader_state(destination, extracted)
            _set_tree_ownership(extracted, css_loader_owner.st_uid, css_loader_owner.st_gid)
            _fsync_tree(extracted)
            journal = {
                "schemaVersion": 1,
                "token": transaction_token,
                "themeId": theme_id,
                "themeName": theme_name,
                "version": version,
                "hadPrevious": destination.exists(),
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


def _finish_rollback(work: Path, journal: dict[str, object], themes_root: Path) -> None:
    destination = themes_root / str(journal["themeName"])
    backup = work / "previous"
    rejected = work / "rejected"
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ThemePackageError("rollback_failed", "Installed theme path is unsafe")
    try:
        if destination.exists():
            _durable_replace(destination, rejected)
        if journal["hadPrevious"]:
            if backup.is_symlink() or not backup.is_dir():
                raise OSError("Previous theme backup is unavailable")
            _durable_replace(backup, destination)
    except OSError as error:
        if rejected.exists() and not destination.exists():
            try:
                _durable_replace(rejected, destination)
            except OSError:
                pass
        raise ThemePackageError(
            "rollback_failed",
            "The previous theme could not be restored",
        ) from error
    _write_journal(work / "transaction.json", {**journal, "state": "rolled_back"})


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


def commit_theme_install(token: str, themes_root: str | Path) -> dict[str, object]:
    root = Path(themes_root)
    with _mutation_lock(root):
        work = _transaction_path(root, token)
        journal = _read_transaction(work, token)
        if journal["state"] != "swapped":
            raise ThemePackageError("invalid_transaction", "Theme transaction is already complete")
        _write_journal(work / "transaction.json", {**journal, "state": "committed"})
        _remove_terminal_transaction(work)
        return {"ok": True, "code": "committed"}


def rollback_theme_install(token: str, themes_root: str | Path) -> dict[str, object]:
    root = Path(themes_root)
    with _mutation_lock(root):
        work = _transaction_path(root, token)
        journal = _read_transaction(work, token)
        if journal["state"] != "swapped":
            raise ThemePackageError("invalid_transaction", "Theme transaction is already complete")
        _finish_rollback(work, journal, root)
        return {"ok": True, "code": "rolled_back"}


def acknowledge_theme_rollback(token: str, themes_root: str | Path) -> dict[str, object]:
    root = Path(themes_root)
    with _mutation_lock(root):
        work = _transaction_path(root, token)
        journal = _read_transaction(work, token)
        if journal["state"] != "rolled_back":
            raise ThemePackageError("invalid_transaction", "Theme rollback is not ready to acknowledge")
        _write_journal(work / "transaction.json", {**journal, "state": "acknowledged"})
        _remove_terminal_transaction(work)
        return {"ok": True, "code": "acknowledged"}


def _recover_transaction(work: Path, journal: dict[str, object], root: Path) -> bool:
    state = journal["state"]
    if state in ("acknowledged", "committed"):
        _remove_terminal_transaction(work)
        return False
    if state == "rolled_back":
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
        _write_journal(work / "transaction.json", {**journal, "state": "rolled_back"})
        return True
    if state == "staged" and not journal["hadPrevious"] and not destination.exists():
        if (work / "extracted").exists():
            _durable_remove_tree(work)
            return False
        _write_journal(work / "transaction.json", {**journal, "state": "rolled_back"})
        return True
    if journal["hadPrevious"] and not destination.exists() and backup.exists():
        _durable_replace(backup, destination)
        if state == "staged" and (work / "extracted").exists():
            _durable_remove_tree(work)
            return False
        _write_journal(work / "transaction.json", {**journal, "state": "rolled_back"})
        return True
    if journal["hadPrevious"] and not backup.exists() and destination.exists() and installed_version != new_version:
        _write_journal(work / "transaction.json", {**journal, "state": "rolled_back"})
        return True

    _finish_rollback(work, journal, root)
    return True


def recover_theme_transactions(themes_root: str | Path) -> list[dict[str, object]]:
    root = Path(themes_root)
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
            if _recover_transaction(work, journal, root):
                try:
                    current = _read_transaction(work)
                except ThemePackageError as error:
                    raise ThemePackageError(
                        "invalid_journal",
                        "A theme transaction journal requires recovery",
                    ) from error
                pending.append(_pending_recovery(work, current, root))
    return pending


def prepare_bundled_theme(
    theme_id: str,
    *,
    plugin_root: str | Path,
    themes_root: str | Path,
) -> dict[str, object]:
    registered = _BUNDLED_THEMES.get(theme_id)
    if registered is None:
        raise ThemePackageError("unsupported_theme", "Theme is not bundled with Panel de Control")
    packages = Path(plugin_root) / "theme-packages"
    descriptor = _read_json(packages / registered.descriptor_name, "invalid_descriptor")
    declared_id, _, _, artifact_name, _, _ = _descriptor(descriptor)
    if declared_id != theme_id:
        raise ThemePackageError("identity_mismatch", "Bundled theme id does not match its descriptor")
    return prepare_theme_archive(packages / artifact_name, descriptor, themes_root)
