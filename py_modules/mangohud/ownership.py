from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
import stat
import sys
import tempfile


_BACKUP_SUFFIX = ".pdc-backup"
_MANAGED_SUFFIX = ".pdc-managed"
_PHASES = {"installing", "managed", "updating", "restoring"}


@dataclass(frozen=True)
class FileMutation:
    content: str | None


class HudOwnershipConflict(OSError):
    def __init__(
        self,
        reason: str,
        expected_hash: str | None = None,
        actual_hash: str | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash


def read_text(path):
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd) as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def _sha256(text):
    if text is None:
        return None
    return hashlib.sha256(text.encode()).hexdigest()


def _valid_hash(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _ensure_directory(path, owner):
    missing = []
    current = path
    while current and not os.path.exists(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    os.makedirs(path, exist_ok=True)
    if owner is not None:
        for created in reversed(missing):
            os.chown(created, *owner)


def _fsync_directory(path):
    directory = os.path.dirname(path) or os.curdir
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _remove(path):
    os.remove(path)
    _fsync_directory(path)


def _replace(source, destination):
    os.replace(source, destination)
    _fsync_directory(destination)
    if os.path.dirname(source) != os.path.dirname(destination):
        _fsync_directory(source)


def _apply_metadata(fd, source):
    metadata = os.stat(source, follow_symlinks=False)
    os.fchown(fd, metadata.st_uid, metadata.st_gid)
    os.fchmod(fd, stat.S_IMODE(metadata.st_mode))
    if hasattr(os, "listxattr"):
        for name in os.listxattr(source, follow_symlinks=False):
            value = os.getxattr(source, name, follow_symlinks=False)
            os.setxattr(fd, name, value)
    os.utime(fd, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))


def _write_atomic(path, text, owner=None, metadata_from=None):
    directory = os.path.dirname(path)
    if directory:
        _ensure_directory(directory, owner)
    fd, tmp = tempfile.mkstemp(prefix=".presets.", dir=directory or None, text=True)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
            handle.flush()
            if metadata_from is not None:
                _apply_metadata(handle.fileno(), metadata_from)
            else:
                os.fchmod(handle.fileno(), 0o644)
            if owner is not None and metadata_from is None:
                os.fchown(handle.fileno(), *owner)
            os.fsync(handle.fileno())
        _replace(tmp, path)
    except Exception:
        try:
            _remove(tmp)
        except OSError:
            pass
        raise


def _marker_text(managed_hash, rollback, phase="managed", previous_hash=None):
    marker = {
        "version": 1,
        "phase": phase,
        "managed_sha256": managed_hash,
        "rollback": {
            "present": rollback is not None,
            "sha256": _sha256(rollback),
        },
    }
    if previous_hash is not None:
        marker["previous_sha256"] = previous_hash
    return json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n"


def _load_marker(path):
    raw = read_text(f"{path}{_MANAGED_SUFFIX}")
    if raw is None:
        return None
    try:
        marker = json.loads(raw)
    except (TypeError, ValueError) as exc:
        if raw.strip() in {"1", "managed"}:
            return {"version": 0, "phase": "legacy"}
        raise HudOwnershipConflict("marker_invalid") from exc
    if not isinstance(marker, dict) or marker.get("version") != 1:
        raise HudOwnershipConflict("marker_invalid")
    phase = marker.get("phase")
    rollback = marker.get("rollback")
    if (
        phase not in _PHASES
        or not _valid_hash(marker.get("managed_sha256"))
        or not isinstance(rollback, dict)
        or not isinstance(rollback.get("present"), bool)
        or (
            rollback["present"]
            and not _valid_hash(rollback.get("sha256"))
        )
        or (
            not rollback["present"]
            and rollback.get("sha256") is not None
        )
        or (
            phase == "updating"
            and not _valid_hash(marker.get("previous_sha256"))
        )
    ):
        raise HudOwnershipConflict("marker_invalid")
    return marker


def _rollback_text(path, marker):
    rollback = marker.get("rollback") or {}
    backup = read_text(f"{path}{_BACKUP_SUFFIX}")
    if rollback.get("present"):
        expected = rollback.get("sha256")
        actual = _sha256(backup)
        if backup is None or actual != expected:
            raise HudOwnershipConflict("rollback_mismatch", expected, actual)
        return backup
    if backup is not None:
        raise HudOwnershipConflict("unexpected_rollback", None, _sha256(backup))
    return None


def _resume_install(path, desired, marker, owner):
    marker_path = f"{path}{_MANAGED_SUFFIX}"
    backup_path = f"{path}{_BACKUP_SUFFIX}"
    rollback = marker.get("rollback") or {}
    rollback_present = bool(rollback.get("present"))
    rollback_hash = rollback.get("sha256")
    managed_hash = marker.get("managed_sha256")
    current = read_text(path)
    current_hash = _sha256(current)
    if current_hash == managed_hash:
        rollback_content = _rollback_text(path, marker)
    elif current_hash == rollback_hash and (rollback_present or current is None):
        rollback_content = current if rollback_present else None
        backup = read_text(backup_path)
        if rollback_present:
            if backup is None:
                _write_atomic(
                    backup_path,
                    current,
                    owner,
                    metadata_from=path,
                )
            elif _sha256(backup) != rollback_hash:
                raise HudOwnershipConflict(
                    "rollback_mismatch", rollback_hash, _sha256(backup)
                )
        elif backup is not None:
            raise HudOwnershipConflict("unexpected_rollback", None, _sha256(backup))
        _write_atomic(path, desired, owner)
    else:
        reason = "managed_content_missing" if current is None else "managed_content_mismatch"
        raise HudOwnershipConflict(reason, managed_hash, current_hash)
    _write_atomic(
        marker_path,
        _marker_text(managed_hash, rollback_content),
        owner,
    )
    return FileMutation(read_text(path))


def _resume_update(path, desired, marker, owner):
    marker_path = f"{path}{_MANAGED_SUFFIX}"
    managed_hash = marker.get("managed_sha256")
    previous_hash = marker.get("previous_sha256")
    rollback = _rollback_text(path, marker)
    current = read_text(path)
    current_hash = _sha256(current)
    if current_hash == previous_hash:
        _write_atomic(path, desired, owner)
    elif current_hash == managed_hash:
        pass
    else:
        reason = "managed_content_missing" if current is None else "managed_content_mismatch"
        raise HudOwnershipConflict(reason, managed_hash, current_hash)
    _write_atomic(marker_path, _marker_text(managed_hash, rollback), owner)
    return FileMutation(read_text(path))


def _write_managed(path, desired, owner=None, replace_conflict=False):
    marker_path = f"{path}{_MANAGED_SUFFIX}"
    backup_path = f"{path}{_BACKUP_SUFFIX}"
    marker = None if replace_conflict else _load_marker(path)
    current = read_text(path)
    desired_hash = _sha256(desired)
    if marker is None and not replace_conflict:
        if os.path.exists(backup_path):
            raise HudOwnershipConflict("orphan_rollback")
        if current is not None:
            raise HudOwnershipConflict(
                "external_config",
                desired_hash,
                _sha256(current),
            )
    if marker is not None:
        if marker.get("phase") == "legacy":
            desired_hash = _sha256(desired)
            current_hash = _sha256(current)
            if current_hash != desired_hash:
                raise HudOwnershipConflict(
                    "legacy_content_mismatch", desired_hash, current_hash
                )
            rollback = read_text(backup_path)
            _write_atomic(
                marker_path,
                _marker_text(desired_hash, rollback),
                owner,
            )
            return FileMutation(current)
        if marker.get("phase") == "installing":
            rollback_meta = marker.get("rollback") or {}
            rollback_present = bool(rollback_meta.get("present"))
            if (
                marker.get("managed_sha256") != desired_hash
                and _sha256(current) == rollback_meta.get("sha256")
                and (rollback_present or current is None)
            ):
                _write_atomic(
                    marker_path,
                    _marker_text(
                        desired_hash,
                        current if rollback_present else None,
                        phase="installing",
                    ),
                    owner,
                )
                marker = _load_marker(path)
            result = _resume_install(path, desired, marker, owner)
            if marker.get("managed_sha256") == desired_hash:
                return result
            marker = _load_marker(path)
            current = read_text(path)
        elif marker.get("phase") == "updating":
            if (
                marker.get("managed_sha256") != desired_hash
                and _sha256(current) == marker.get("previous_sha256")
            ):
                rollback = _rollback_text(path, marker)
                _write_atomic(
                    marker_path,
                    _marker_text(
                        desired_hash,
                        rollback,
                        phase="updating",
                        previous_hash=marker["previous_sha256"],
                    ),
                    owner,
                )
                marker = _load_marker(path)
            result = _resume_update(path, desired, marker, owner)
            if marker.get("managed_sha256") == desired_hash:
                return result
            marker = _load_marker(path)
            current = read_text(path)
        expected = marker.get("managed_sha256")
        actual = _sha256(current)
        if current is None:
            raise HudOwnershipConflict("managed_content_missing", expected, actual)
        if actual != expected:
            raise HudOwnershipConflict("managed_content_mismatch", expected, actual)
        rollback = _rollback_text(path, marker)
    else:
        rollback = current
    if marker is None:
        _write_atomic(
            marker_path,
            _marker_text(desired_hash, rollback, phase="installing"),
            owner,
        )
        if rollback is not None:
            _write_atomic(
                backup_path,
                rollback,
                owner,
                metadata_from=path,
            )
        elif replace_conflict and os.path.exists(backup_path):
            _remove(backup_path)
    elif current != desired:
        _write_atomic(
            marker_path,
            _marker_text(
                desired_hash,
                rollback,
                phase="updating",
                previous_hash=_sha256(current),
            ),
            owner,
        )
    elif marker is not None and marker.get("phase") == "managed":
        return FileMutation(current)
    if current != desired:
        _write_atomic(path, desired, owner)
    _write_atomic(marker_path, _marker_text(desired_hash, rollback), owner)
    return FileMutation(read_text(path))


def _restore_managed(path, owner=None):
    marker_path = f"{path}{_MANAGED_SUFFIX}"
    backup_path = f"{path}{_BACKUP_SUFFIX}"
    marker = _load_marker(path)
    if marker is None:
        return FileMutation(read_text(path))
    current = read_text(path)
    expected = marker.get("managed_sha256")
    actual = _sha256(current)
    rollback_meta = marker.get("rollback") or {}
    rollback_present = bool(rollback_meta.get("present"))
    rollback_hash = rollback_meta.get("sha256")
    if (
        marker.get("phase") == "installing"
        and actual == rollback_hash
        and (rollback_present or current is None)
    ):
        backup = read_text(backup_path)
        if backup is not None and _sha256(backup) != rollback_hash:
            raise HudOwnershipConflict(
                "rollback_mismatch", rollback_hash, _sha256(backup)
            )
        if backup is not None:
            _remove(backup_path)
        _remove(marker_path)
        return FileMutation(current)
    if marker.get("phase") == "restoring":
        if rollback_present and actual == rollback_hash:
            if os.path.exists(backup_path):
                raise HudOwnershipConflict(
                    "unexpected_rollback", None, _sha256(read_text(backup_path))
                )
            _remove(marker_path)
            return FileMutation(current)
        if not rollback_present and current is None:
            _remove(marker_path)
            return FileMutation(None)
    if marker.get("phase") == "updating" and actual == marker.get("previous_sha256"):
        expected = actual
    if current is None:
        raise HudOwnershipConflict("managed_content_missing", expected, actual)
    if actual != expected:
        raise HudOwnershipConflict("managed_content_mismatch", expected, actual)
    rollback = _rollback_text(path, marker)
    _write_atomic(
        marker_path,
        _marker_text(expected, rollback, phase="restoring"),
        owner,
    )
    if rollback is None:
        _remove(path)
    else:
        _replace(backup_path, path)
    _remove(marker_path)
    return FileMutation(read_text(path))


def _relinquish_managed(path):
    for suffix in (_MANAGED_SUFFIX, _BACKUP_SUFFIX):
        try:
            _remove(f"{path}{suffix}")
        except FileNotFoundError:
            pass
    return FileMutation(read_text(path))


@contextmanager
def _pinned_target(path, trusted_root, owner, create_parent):
    if trusted_root is None or sys.platform != "linux":
        yield path
        return
    if not os.path.isdir("/proc/self/fd"):
        raise OSError("The Linux proc filesystem is required for safe HUD writes")
    root = os.path.realpath(trusted_root)
    target = os.path.abspath(path)
    try:
        relative = os.path.relpath(target, root)
        if relative == os.pardir or relative.startswith(f"{os.pardir}{os.sep}"):
            raise OSError("MangoHud presets path is outside the trusted user home")
    except ValueError as exc:
        raise OSError("Invalid MangoHud presets path") from exc
    parts = relative.split(os.sep)
    filename = parts.pop()
    if not filename or any(part in ("", os.curdir, os.pardir) for part in parts):
        raise OSError("Invalid MangoHud presets path")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory_fd = os.open(root, flags)
    try:
        for part in parts:
            try:
                next_fd = os.open(part, flags, dir_fd=directory_fd)
            except FileNotFoundError:
                if not create_parent:
                    yield None
                    return
                os.mkdir(part, mode=0o755, dir_fd=directory_fd)
                if owner is not None:
                    os.chown(
                        part,
                        *owner,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                os.fsync(directory_fd)
                next_fd = os.open(part, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        yield f"/proc/self/fd/{directory_fd}/{filename}"
    finally:
        os.close(directory_fd)


def write_managed(
    path,
    desired,
    owner=None,
    replace_conflict=False,
    trusted_root=None,
):
    with _pinned_target(path, trusted_root, owner, True) as target:
        return _write_managed(target, desired, owner, replace_conflict)


def restore_managed(path, owner=None, trusted_root=None):
    with _pinned_target(path, trusted_root, owner, False) as target:
        return FileMutation(None) if target is None else _restore_managed(target, owner)


def relinquish_managed(path, trusted_root=None):
    with _pinned_target(path, trusted_root, None, False) as target:
        return FileMutation(None) if target is None else _relinquish_managed(target)
