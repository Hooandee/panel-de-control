import json
import os
import stat
import tempfile
import threading
import time
import uuid
from pathlib import Path


_SCHEMA_VERSION = 1
_MAX_JOURNAL_BYTES = 2 * 1024 * 1024
# Far beyond any CSS Loader call timeout: an older unsettled journal was left by an unloaded frontend.
_UNSETTLED_MUTATION_TTL_S = 120
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


def _exact_keys(value, required, optional=()):
    return isinstance(value, dict) and set(value) in (
        set(required),
        set(required) | set(optional),
    )


def _named(value):
    return isinstance(value, dict) and isinstance(value.get("name"), str) and bool(value["name"].strip())


def _strings(value, keys):
    return all(isinstance(value.get(key), str) for key in keys)


def _normalize_patch(value):
    if (
        not _named(value)
        or not _strings(value, ("defaultValue", "value", "type", "rawType"))
        or not isinstance(value.get("options"), list)
        or not all(isinstance(option, str) for option in value["options"])
    ):
        return None
    return {
        "name": value["name"],
        "defaultValue": value["defaultValue"],
        "value": value["value"],
        "options": value["options"],
        "type": value["type"],
        "rawType": value["rawType"],
    }


def _normalize_theme(value):
    if (
        not _named(value)
        or not _strings(value, ("id", "displayName", "version", "author"))
        or not isinstance(value.get("enabled"), bool)
        or not isinstance(value.get("patches"), list)
    ):
        return None
    patches = [_normalize_patch(patch) for patch in value["patches"]]
    if any(patch is None for patch in patches):
        return None
    if len({patch["name"] for patch in patches}) != len(patches):
        return None
    return {
        "id": value["id"],
        "name": value["name"],
        "displayName": value["displayName"],
        "version": value["version"],
        "author": value["author"],
        "enabled": value["enabled"],
        "patches": patches,
    }


def _parse_snapshot(snapshot):
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("status") != "ready"
        or not isinstance(snapshot.get("themes"), list)
    ):
        raise ThemeActivationJournalError(
            "invalid_snapshot",
            "Theme activation snapshot has an invalid shape",
        )
    themes = [_normalize_theme(theme) for theme in snapshot["themes"]]
    if any(theme is None for theme in themes):
        raise ThemeActivationJournalError(
            "invalid_snapshot",
            "Theme activation snapshot has a malformed theme",
        )
    normalized = {"status": "ready", "themes": themes}
    encoded = json.dumps(normalized, separators=(",", ":")).encode("utf-8")
    if len(encoded) > _MAX_JOURNAL_BYTES:
        raise ThemeActivationJournalError(
            "invalid_snapshot",
            f"Theme activation snapshot is too large ({len(encoded)} bytes)",
        )
    return normalized


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
            "started_monotonic_ns",
            "snapshot",
        })
        or journal["phase"] not in ("mutating", "settled")
        or not _validate_transaction(journal["boot_id"])
        or not isinstance(journal["started_monotonic_ns"], int)
    ):
        raise ThemeActivationJournalError(
            "invalid_journal",
            "Theme activation recovery journal is invalid",
        )
    try:
        journal["snapshot"] = _parse_snapshot(journal["snapshot"])
    except ThemeActivationJournalError as error:
        raise ThemeActivationJournalError(
            "invalid_journal",
            "Theme activation recovery journal is invalid",
        ) from error
    return journal


def _read_journal_or_quarantine(path: Path):
    """An unreadable journal cannot restore anything; moving it aside unblocks theme changes."""
    try:
        return _read_journal(path)
    except ThemeActivationJournalError as error:
        if error.code != "invalid_journal":
            raise
        try:
            os.replace(path, path.with_name(f"{path.name}.quarantined"))
            _fsync_directory(path.parent)
        except OSError:
            raise error from None
        return None


def begin_theme_activation(snapshot, journal_path):
    path = Path(journal_path)
    snapshot = _parse_snapshot(snapshot)
    boot_id = _boot_id()
    if boot_id is None:
        raise ThemeActivationJournalError(
            "boot_identity_unavailable",
            "System boot identity is unavailable",
        )
    with _lock:
        existing = _read_journal_or_quarantine(path)
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
            "started_monotonic_ns": time.monotonic_ns(),
            "snapshot": snapshot,
        })
    return {"ok": True, "code": "prepared", "transaction": transaction}


def get_theme_activation_recovery(journal_path):
    with _lock:
        journal = _read_journal_or_quarantine(Path(journal_path))
    if journal is None or journal["phase"] == "completed":
        return None
    age_s = (time.monotonic_ns() - journal["started_monotonic_ns"]) / 1e9
    boot_id = _boot_id()
    return {
        "transaction": journal["transaction"],
        "snapshot": journal["snapshot"],
        "recoverable": (
            journal["phase"] == "settled"
            or (boot_id is not None and journal["boot_id"] != boot_id)
            or age_s > _UNSETTLED_MUTATION_TTL_S
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


def theme_activation_phase(journal_path):
    try:
        with _lock:
            journal = _read_journal(Path(journal_path))
    except ThemeActivationJournalError:
        return "invalid"
    return None if journal is None else journal["phase"]
