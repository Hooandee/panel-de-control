import copy
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path


EVENTS = {
    "scan_started", "scan_completed", "scan_failed", "scan_cancelled",
    "cleanup_started", "cleanup_completed", "cleanup_failed", "interrupted",
}
SOURCES = {"none", "screenshots", "recordings", "clips", "measurement"}
REASONS = {
    "none", "steam_rejected", "invalid_response", "item_changed",
    "active_recording", "steam_api_error", "invalid_item", "measurement_failed",
    "section_closed", "interrupted",
}
OPERATION_ID = re.compile(r"(?:[a-f0-9]{4}-){7}[a-f0-9]{4}")


class SteamMediaDiagnostics:
    def __init__(self, state_dir=None, logger=None):
        self._state_dir = Path(state_dir) if state_dir is not None else None
        self._logger = logger
        self._lock = threading.RLock()
        self._diagnostic = {
            "schema_version": 1, "phase": "idle", "last_operation_id": None,
            "interrupted": False, "events": [], "persistence_error": None,
        }
        self._load_history()

    def diagnostics(self):
        with self._lock:
            return copy.deepcopy(self._diagnostic)

    def record(self, event, operation_id, count=0, errors=0, source="none", reason="none"):
        if (
            event not in EVENTS or event == "interrupted"
            or not isinstance(operation_id, str) or not OPERATION_ID.fullmatch(operation_id)
            or type(count) is not int or not 0 <= count <= 10_000
            or type(errors) is not int or not 0 <= errors <= 10_000
            or event.startswith("cleanup_") and errors > count
            or source not in SOURCES or reason not in REASONS
        ):
            return False
        phase = "cleanup" if event.startswith("cleanup_") else "scan"
        item = {
            "event": event, "operation_id": operation_id, "phase": phase,
            "at": int(time.time()), "source": source, "reason": reason,
            "count": count, "errors": errors,
        }
        if event == "cleanup_completed":
            item["deleted"] = count - errors
        with self._lock:
            if event.endswith("_started"):
                self._diagnostic["last_operation_id"] = operation_id
                self._diagnostic["phase"] = phase
            elif self._diagnostic["last_operation_id"] is None:
                self._diagnostic["last_operation_id"] = operation_id
            is_current = self._diagnostic["last_operation_id"] == operation_id
            terminal = (
                event.endswith("_completed") or event == "scan_cancelled"
                or event == "scan_failed" and source == "none"
                or event == "cleanup_failed" and source == "none"
            )
            if is_current and terminal:
                self._diagnostic["phase"] = "idle"
            self._diagnostic["events"] = (self._diagnostic["events"] + [item])[-120:]
        if self._logger:
            try:
                self._logger.info("steam_media " + json.dumps(item, separators=(",", ":")))
            except Exception:
                pass
        self._save_history()
        return True

    def _load_history(self):
        if self._state_dir is None:
            return
        interrupted = False
        try:
            with open(self._state_dir / "steam_media_history.json", "rb") as source:
                raw = source.read(128 * 1024 + 1)
            if len(raw) > 128 * 1024:
                raise ValueError("oversized_history")
            document = json.loads(raw)
            if not isinstance(document, dict) or document.get("schema_version") != 1 or not isinstance(document.get("events"), list):
                raise ValueError("invalid_history")
            allowed = []
            for item in document["events"][-120:]:
                if (
                    not isinstance(item, dict) or item.get("event") not in EVENTS
                    or not isinstance(item.get("operation_id"), str) or not OPERATION_ID.fullmatch(item["operation_id"])
                    or item.get("phase") not in {"scan", "cleanup"} or type(item.get("at")) is not int
                ):
                    self._diagnostic["persistence_error"] = "io_error"
                    continue
                event = {key: item[key] for key in ("event", "operation_id", "phase", "at")}
                if item.get("source") in SOURCES:
                    event["source"] = item["source"]
                if item.get("reason") in REASONS:
                    event["reason"] = item["reason"]
                for key in ("count", "errors", "deleted"):
                    if type(item.get(key)) is int and 0 <= item[key] <= 10_000:
                        event[key] = item[key]
                allowed.append(event)
            phase = document.get("phase")
            self._diagnostic["events"] = allowed
            stored_operation_id = document.get("last_operation_id")
            stored_operation_is_valid = (
                isinstance(stored_operation_id, str)
                and OPERATION_ID.fullmatch(stored_operation_id)
                and any(
                    item["event"].endswith("_started")
                    and item["operation_id"] == stored_operation_id
                    for item in allowed
                )
            )
            if stored_operation_is_valid:
                self._diagnostic["last_operation_id"] = stored_operation_id
            else:
                self._diagnostic["last_operation_id"] = allowed[-1]["operation_id"] if allowed else None
                if phase in {"scan", "cleanup"}:
                    self._diagnostic["persistence_error"] = "io_error"
            self._diagnostic["interrupted"] = document.get("interrupted") is True or phase in {"scan", "cleanup"}
            self._diagnostic["phase"] = "idle"
            if phase in {"scan", "cleanup"} and stored_operation_is_valid:
                operation_id = stored_operation_id
                if not any(item["event"] == "interrupted" and item["operation_id"] == operation_id for item in allowed):
                    self._diagnostic["events"] = (allowed + [{
                        "event": "interrupted", "operation_id": operation_id, "phase": phase,
                        "at": int(time.time()), "source": "none", "reason": "interrupted",
                        "count": 0, "errors": 0,
                    }])[-120:]
                    interrupted = True
        except FileNotFoundError:
            return
        except (OSError, TypeError, ValueError):
            self._diagnostic["persistence_error"] = "io_error"
        if interrupted:
            self._save_history()

    def _save_history(self):
        if self._state_dir is None:
            return
        temporary = None
        with self._lock:
            try:
                self._state_dir.mkdir(parents=True, exist_ok=True)
                temporary = self._state_dir / f".steam_media_{uuid.uuid4().hex}.tmp"
                document = copy.deepcopy(self._diagnostic)
                with open(temporary, "x", encoding="utf-8") as output:
                    json.dump(document, output, separators=(",", ":"))
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self._state_dir / "steam_media_history.json")
                self._diagnostic["persistence_error"] = None
            except OSError:
                self._diagnostic["persistence_error"] = "io_error"
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
