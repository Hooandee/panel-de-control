import json
import os
import stat
import tempfile
import threading
import uuid
from pathlib import Path


_SCHEMA_VERSION = 1
_MAX_JOURNAL_BYTES = 512 * 1024
_MAX_THEMES = 128
_MAX_PATCHES = 128
_MAX_OPTIONS = 128
_MAX_TEXT_BYTES = 4096
_lock = threading.RLock()


class ThemeActivationJournalError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _boot_id():
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def _text(value, *, non_empty=False):
    return (
        isinstance(value, str)
        and (not non_empty or bool(value.strip()))
        and len(value.encode("utf-8")) <= _MAX_TEXT_BYTES
    )


def _exact_keys(value, required, optional=()):
    return isinstance(value, dict) and set(value) in (
        set(required),
        set(required) | set(optional),
    )


def _valid_patch(value):
    if not _exact_keys(value, {
        "name",
        "defaultValue",
        "value",
        "options",
        "type",
        "rawType",
    }):
        return False
    options = value["options"]
    return (
        _text(value["name"], non_empty=True)
        and _text(value["defaultValue"])
        and _text(value["value"])
        and isinstance(options, list)
        and len(options) <= _MAX_OPTIONS
        and all(_text(option) for option in options)
        and _text(value["type"], non_empty=True)
        and _text(value["rawType"], non_empty=True)
    )


def _valid_theme(value):
    if not _exact_keys(value, {
        "id",
        "name",
        "displayName",
        "version",
        "author",
        "enabled",
        "patches",
    }):
        return False
    patches = value["patches"]
    if (
        not _text(value["id"])
        or not _text(value["name"], non_empty=True)
        or not _text(value["displayName"])
        or not _text(value["version"])
        or not _text(value["author"])
        or not isinstance(value["enabled"], bool)
        or not isinstance(patches, list)
        or len(patches) > _MAX_PATCHES
        or not all(_valid_patch(patch) for patch in patches)
    ):
        return False
    patch_names = [patch["name"] for patch in patches]
    return len(patch_names) == len(set(patch_names))


def _validate_snapshot(snapshot):
    if not _exact_keys(
        snapshot,
        {"status", "backendVersion", "themes"},
        {"pluginVersion"},
    ):
        raise ThemeActivationJournalError(
            "invalid_snapshot",
            "Theme activation snapshot has an invalid shape",
        )
    themes = snapshot["themes"]
    backend_version = snapshot["backendVersion"]
    if (
        snapshot["status"] != "ready"
        or not isinstance(backend_version, int)
        or isinstance(backend_version, bool)
        or backend_version < 9
        or (
            "pluginVersion" in snapshot
            and not _text(snapshot["pluginVersion"])
        )
        or not isinstance(themes, list)
        or len(themes) > _MAX_THEMES
        or not all(_valid_theme(theme) for theme in themes)
    ):
        raise ThemeActivationJournalError(
            "invalid_snapshot",
            "Theme activation snapshot is invalid",
        )
    theme_names = [theme["name"] for theme in themes]
    if len(theme_names) != len(set(theme_names)):
        raise ThemeActivationJournalError(
            "invalid_snapshot",
            "Theme activation snapshot contains duplicate themes",
        )
    encoded = json.dumps(snapshot, separators=(",", ":")).encode("utf-8")
    if len(encoded) > _MAX_JOURNAL_BYTES:
        raise ThemeActivationJournalError(
            "invalid_snapshot",
            "Theme activation snapshot is too large",
        )


def _validate_transaction(transaction):
    if not isinstance(transaction, str):
        return False
    try:
        return str(uuid.UUID(transaction)) == transaction
    except ValueError:
        return False


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_journal(path: Path, journal):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(journal, separators=(",", ":")).encode("utf-8")
    if len(payload) > _MAX_JOURNAL_BYTES:
        raise ThemeActivationJournalError(
            "invalid_snapshot",
            "Theme activation journal is too large",
        )
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _read_journal(path: Path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_JOURNAL_BYTES:
        raise ThemeActivationJournalError(
            "invalid_journal",
            "Theme activation recovery journal is unsafe",
        )
    try:
        with path.open("rb") as stream:
            payload = stream.read(_MAX_JOURNAL_BYTES + 1)
        journal = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ThemeActivationJournalError(
            "invalid_journal",
            "Theme activation recovery journal is invalid",
        ) from error
    if not isinstance(journal, dict) or journal.get("schema_version") != _SCHEMA_VERSION:
        raise ThemeActivationJournalError(
            "invalid_journal",
            "Theme activation recovery journal is invalid",
        )
    if not _validate_transaction(journal.get("transaction")):
        raise ThemeActivationJournalError(
            "invalid_journal",
            "Theme activation recovery journal is invalid",
        )
    if journal.get("phase") == "completed":
        if not _exact_keys(journal, {"schema_version", "transaction", "phase"}):
            raise ThemeActivationJournalError(
                "invalid_journal",
                "Theme activation recovery journal is invalid",
            )
        return journal
    if (
        not _exact_keys(journal, {
            "schema_version",
            "transaction",
            "phase",
            "boot_id",
            "snapshot",
        })
        or journal["phase"] not in ("mutating", "settled")
        or not _text(journal["boot_id"], non_empty=True)
    ):
        raise ThemeActivationJournalError(
            "invalid_journal",
            "Theme activation recovery journal is invalid",
        )
    try:
        _validate_snapshot(journal["snapshot"])
    except ThemeActivationJournalError as error:
        raise ThemeActivationJournalError(
            "invalid_journal",
            "Theme activation recovery journal is invalid",
        ) from error
    return journal


def begin_theme_activation(snapshot, journal_path):
    path = Path(journal_path)
    _validate_snapshot(snapshot)
    boot_id = _boot_id()
    if boot_id is None:
        raise ThemeActivationJournalError(
            "boot_identity_unavailable",
            "System boot identity is unavailable",
        )
    with _lock:
        existing = _read_journal(path)
        if existing is not None and existing["phase"] != "completed":
            raise ThemeActivationJournalError(
                "recovery_pending",
                "A theme activation recovery is already pending",
            )
        transaction = str(uuid.uuid4())
        _write_journal(path, {
            "schema_version": _SCHEMA_VERSION,
            "transaction": transaction,
            "phase": "mutating",
            "boot_id": boot_id,
            "snapshot": snapshot,
        })
    return {"ok": True, "code": "prepared", "transaction": transaction}


def get_theme_activation_recovery(journal_path):
    with _lock:
        journal = _read_journal(Path(journal_path))
    if journal is None or journal["phase"] == "completed":
        return None
    boot_id = _boot_id()
    return {
        "transaction": journal["transaction"],
        "snapshot": journal["snapshot"],
        "recoverable": (
            journal["phase"] == "settled"
            or (boot_id is not None and journal["boot_id"] != boot_id)
        ),
    }


def mark_theme_activation_settled(transaction, journal_path):
    path = Path(journal_path)
    with _lock:
        journal = _read_journal(path)
        if (
            journal is not None
            and journal["phase"] == "completed"
            and journal["transaction"] == transaction
        ):
            return {"ok": True, "code": "settled"}
        if (
            journal is None
            or journal["phase"] == "completed"
            or journal["transaction"] != transaction
        ):
            raise ThemeActivationJournalError(
                "invalid_transaction",
                "Theme activation recovery transaction does not match",
            )
        if journal["phase"] != "settled":
            _write_journal(path, {
                **journal,
                "phase": "settled",
            })
    return {"ok": True, "code": "settled"}


def acknowledge_theme_activation(transaction, journal_path):
    path = Path(journal_path)
    with _lock:
        journal = _read_journal(path)
        if journal is None or journal["transaction"] != transaction:
            raise ThemeActivationJournalError(
                "invalid_transaction",
                "Theme activation recovery transaction does not match",
            )
        if journal["phase"] == "completed":
            return {"ok": True, "code": "acknowledged"}
        if journal["phase"] != "settled":
            raise ThemeActivationJournalError(
                "mutation_unsettled",
                "Theme activation mutation has not settled",
            )
        _write_journal(path, {
            "schema_version": _SCHEMA_VERSION,
            "transaction": transaction,
            "phase": "completed",
        })
    return {"ok": True, "code": "acknowledged"}
