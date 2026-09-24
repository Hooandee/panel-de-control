import copy
import errno
import hashlib
import json
import os
import re
import stat
import threading
import time
import uuid
from contextlib import contextmanager
from itertools import islice
from pathlib import Path

from . import filesystem, vdf
from .activity import process_activity
from .media_diagnostics import SteamMediaDiagnostics


class SteamCleanerError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


KINDS = ("shadercache", "compatdata")
MAX_ENTRIES = 10_000
REASONS = {
    "coverage_incomplete", "library_unavailable", "symlink", "unsafe_path",
    "path_changed", "mount_point", "runtime", "activity_unknown", "active_game",
    "size_unknown", "cancelled", "io_error", "busy", "closed", "invalid_selection",
    "stale_scan", "invalid_plan", "expired_plan", "prefix_confirmation_required",
    "internal_error",
    "permission_denied", "not_found", "disk_full", "interrupted", "partial_delete", "unknown_identity", "active_download", "malformed_data",
    "managed_by_steam", "protected_tool", "tool_in_use", "media_unavailable", "media_incomplete", "media_delete_failed",
}
EVENTS = {"started", "completed", "prepared", "deleted", "skipped", "error", "interrupted"}
PHASES = {"idle", "scan", "prepare", "execute"}
SOURCES = {"library_index", "library", "manifest", "shortcuts", "measure", "history"}
VDF_ERRORS = {"empty", "malformed_vdf", "duplicate_vdf_key", "oversized_vdf", "unicode", "appid_mismatch"}


def opaque(*parts):
    return grouped_id(hashlib.sha256("\0".join(str(part) for part in parts).encode()).hexdigest()[:24])


def grouped_id(value=None):
    value = value or uuid.uuid4().hex
    return "-".join(value[index:index + 4] for index in range(0, len(value), 4))


def clean_name(value):
    return "".join(character for character in str(value) if character.isprintable())[:160] or None


def system_error(error):
    return {
        errno.EACCES: "permission_denied", errno.EPERM: "permission_denied",
        errno.ENOENT: "not_found", errno.ENOSPC: "disk_full",
    }.get(getattr(error, "errno", None), "io_error")


class SteamCleanerService:
    def __init__(self, home, logger=None, state_dir=None, activity_provider=None):
        self._home = Path(home)
        self._logger = logger
        self._state_dir = Path(state_dir) if state_dir is not None else None
        self._activity_provider = activity_provider or (lambda: process_activity(self._home, data_roots=[str(target["path"]) for target in self._targets.values()]))
        self._state_lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._cancelled = threading.Event()
        self._closed = False
        self._targets = {}
        self._sources = {}
        self._library_resolutions = {}
        self._libraries = []
        self._scan_reported = set()
        self._plans = {}
        self._state = {
            "schema_version": 1, "available": False, "status": "idle", "scan_id": None,
            "coverage_complete": False, "entries": [], "libraries": [],
            "totals": {"shadercache": 0, "compatdata": 0, "unknown": 0},
            "progress": {"processed": 0, "total": None}, "error": None, "last_result": None,
        }
        self._diagnostic = {
            "schema_version": 1, "phase": "idle", "last_operation_id": None,
            "interrupted": False, "events": [], "persistence_error": None,
        }
        from .proton import ProtonCleanerService
        self._proton = ProtonCleanerService(home, logger=logger, state_dir=self._state_dir, activity_provider=activity_provider)
        self._media = SteamMediaDiagnostics(self._state_dir, logger)
        self._load_history()

    def get_state(self):
        with self._state_lock:
            return copy.deepcopy(self._state)

    def diagnostics(self):
        with self._state_lock:
            result = copy.deepcopy(self._diagnostic)
        result["proton"] = self._proton.diagnostics()
        result["media"] = self._media.diagnostics()
        return result

    def record_media_event(self, event, operation_id, count=0, errors=0, source="none", reason="none"):
        return self._media.record(event, operation_id, count, errors, source, reason)

    def cancel(self):
        self._cancelled.set()
        self._proton.cancel()
        with self._state_lock:
            self._plans.clear()
        return self.get_state()

    def close(self):
        with self._state_lock:
            self._closed = True
            self._cancelled.set()
            self._plans.clear()
        self._proton.close()
        with self._operation_lock:
            pass

    def get_proton_state(self):
        return self._proton.get_state()

    def inventory_proton(self):
        return self._proton.inventory()

    def prepare_proton(self, scan_id, entry_ids):
        return self._proton.prepare(scan_id, entry_ids)

    def execute_proton(self, plan_id):
        return self._proton.execute(plan_id)

    @contextmanager
    def _operation(self, phase):
        if not self._operation_lock.acquire(blocking=False):
            raise SteamCleanerError("busy")
        try:
            with self._state_lock:
                if self._closed:
                    raise SteamCleanerError("closed")
                self._cancelled.clear()
                operation_id = grouped_id()
                self._diagnostic["phase"] = phase
                self._diagnostic["last_operation_id"] = operation_id
            self._event("started", operation_id, phase)
            yield operation_id
        except SteamCleanerError as error:
            self._event("error", self._diagnostic["last_operation_id"], phase, reason=error.code)
            raise
        except (OSError, ValueError, filesystem.UnsafePath) as error:
            code = getattr(error, "code", "io_error")
            with self._state_lock:
                self._state.update(status="error", error=code)
            self._event("error", self._diagnostic["last_operation_id"], phase, reason=code, system_error=system_error(error))
            raise SteamCleanerError(code) from None
        except Exception:
            with self._state_lock:
                self._state.update(status="error", error="internal_error")
            self._event("error", self._diagnostic["last_operation_id"], phase, reason="internal_error")
            raise SteamCleanerError("internal_error") from None
        finally:
            with self._state_lock:
                self._diagnostic["phase"] = "idle"
            self._save_history()
            self._operation_lock.release()

    def inventory(self):
        with self._operation("scan") as operation_id:
            started = time.monotonic()
            with self._state_lock:
                self._plans.clear()
                self._state.update(status="scanning", scan_id=None, error=None, progress={"processed": 0, "total": None})
            self._targets = {}
            self._sources = {}
            self._library_resolutions = {}
            self._scan_reported = set()
            roots, critical_complete = self._discover()
            shortcuts_complete = True
            self._libraries = roots
            libraries = []
            identities = {}
            entries = []
            mounts = set()
            mount_error = None
            try:
                mounts = filesystem.mount_points()
            except filesystem.UnsafePath as error:
                mount_error = error.code
            labels = [self._library_label(root, mounts, index) for index, root in enumerate(roots)]
            for root in roots:
                label = labels[len(libraries)]
                if labels.count(label) > 1:
                    label = f"{label} {labels[:len(libraries) + 1].count(label)}"
                library = {"id": opaque(root), "label": label, "available": False, "reason": None,
                           "internal": not mount_error and not libraries and self._internal_library(root, mounts)}
                steamapps = root / "steamapps"
                try:
                    with filesystem.open_directory(str(steamapps)):
                        pass
                    self._remember(steamapps)
                    library["available"] = True
                    if not self._read_manifests(root, identities):
                        critical_complete = False
                    if not self._read_shortcuts(root, identities):
                        shortcuts_complete = False
                except (OSError, filesystem.UnsafePath) as error:
                    critical_complete = False
                    library["reason"] = "symlink" if any(path.is_symlink() for path in (steamapps, *steamapps.parents)) else "library_unavailable"
                    self._scan_issue("library", library["reason"], error, library["id"])
                libraries.append(library)
            for root, library in zip(roots, libraries):
                if len(entries) >= MAX_ENTRIES:
                    critical_complete = False
                    break
                if not library["available"]:
                    continue
                for kind in KINDS:
                    category = root / "steamapps" / kind
                    try:
                        value = category.lstat()
                    except FileNotFoundError:
                        continue
                    except OSError:
                        critical_complete = False
                        entries.append(self._entry(category, "unknown", kind, library, "unsafe_path"))
                        continue
                    if stat.S_ISLNK(value.st_mode):
                        entries.append(self._entry(category, "unknown", kind, library, "symlink"))
                        continue
                    if not stat.S_ISDIR(value.st_mode):
                        entries.append(self._entry(category, "unknown", kind, library, "unsafe_path"))
                        continue
                    try:
                        children = sorted(islice(category.iterdir(), MAX_ENTRIES + 1), key=lambda path: path.name)
                        if len(entries) + len(children) > MAX_ENTRIES:
                            critical_complete = False
                            self._scan_issue("measure", "size_unknown", library_id=library["id"])
                    except OSError:
                        critical_complete = False
                        entries.append(self._entry(category, "unknown", kind, library, "unsafe_path"))
                        continue
                    for path in children:
                        if len(entries) >= MAX_ENTRIES:
                            critical_complete = False
                            break
                        if self._cancelled.is_set():
                            critical_complete = False
                            break
                        appid = path.name if re.fullmatch(r"[0-9]{1,10}", path.name) else "unknown"
                        entry = self._entry(path, appid, kind, library)
                        reason = mount_error
                        if appid == "unknown" or appid == "0" or int(appid) > 0xFFFFFFFF:
                            reason = "unsafe_path"
                        try:
                            value = path.lstat()
                            if stat.S_ISLNK(value.st_mode):
                                reason = "symlink"
                            elif not stat.S_ISDIR(value.st_mode):
                                reason = "unsafe_path"
                            if not reason:
                                tree = filesystem.inspect_tree(path, mounts, self._cancelled)
                                entry["bytes"] = tree["bytes"]
                                self._targets[entry["id"]] = {"path": path, "tree": filesystem.tree_summary(tree)}
                        except filesystem.UnsafePath as error:
                            reason = error.code
                        except OSError:
                            reason = "size_unknown"
                        entry["blocked_reason"] = reason
                        entries.append(entry)
                        with self._state_lock:
                            self._state["progress"]["processed"] = len(entries)
            activity = self._activity()
            totals = {"shadercache": 0, "compatdata": 0, "unknown": 0}
            for entry in entries:
                known = identities.get(entry["appid"])
                if known:
                    entry.update(name=known["name"], installation=known["installation"])
                    if known.get("runtime"):
                        entry["blocked_reason"] = entry["blocked_reason"] or "runtime"
                    elif known["installation"] == "unknown":
                        entry["blocked_reason"] = entry["blocked_reason"] or "unknown_identity"
                    elif known["installation"] == "non_steam" and not shortcuts_complete:
                        entry["requires_manual_selection"] = True
                elif critical_complete and entry["appid"].isdecimal() and int(entry["appid"]) < 0x80000000:
                    entry["installation"] = "not_installed"
                elif critical_complete and entry["installation"] == "unknown":
                    if shortcuts_complete:
                        entry["blocked_reason"] = entry["blocked_reason"] or "unknown_identity"
                    else:
                        entry["requires_manual_selection"] = True
                if entry["name"] is None:
                    entry["warnings"].append("unknown_identity")
                if entry["bytes"] is None:
                    totals["unknown"] += 1
                    entry["warnings"].append("size_unknown")
                else:
                    totals[entry["kind"]] += entry["bytes"]
                reason = self._activity_reason(entry, activity)
                incomplete_identity = (
                    "coverage_incomplete"
                    if not critical_complete and not known
                    else None
                )
                entry["blocked_reason"] = (
                    entry["blocked_reason"] or incomplete_identity or reason
                )
                target = self._targets.get(entry["id"])
                if target and any(str(other).startswith(str(target["path"]) + os.sep) for other in roots):
                    entry["blocked_reason"] = "unsafe_path"
                if entry["blocked_reason"]:
                    self._scan_issue("measure", entry["blocked_reason"], library_id=entry["library_id"], appid=entry["appid"])
            with self._state_lock:
                self._state.update(
                    available=any(library["available"] for library in libraries),
                    status="cancelled" if self._cancelled.is_set() else "ready",
                    scan_id=grouped_id(), coverage_complete=bool(roots) and critical_complete and shortcuts_complete,
                    entries=entries, libraries=libraries, totals=totals,
                    progress={"processed": len(entries), "total": len(entries)},
                )
            self._event("completed", operation_id, "scan", scan_id=self._state["scan_id"], count=len(entries), duration_ms=int((time.monotonic() - started) * 1000), reason="cancelled" if self._cancelled.is_set() else None)
            return self.get_state()

    def prepare(self, scan_id, entry_ids):
        with self._operation("prepare") as operation_id:
            with self._state_lock:
                if not isinstance(scan_id, str) or scan_id != self._state["scan_id"]:
                    raise SteamCleanerError("stale_scan")
                entries = {entry["id"]: entry for entry in self._state["entries"]}
            if not isinstance(entry_ids, list) or not entry_ids or len(entry_ids) > 5000 or any(not isinstance(value, str) or value not in entries for value in entry_ids) or len(set(entry_ids)) != len(entry_ids):
                raise SteamCleanerError("invalid_selection")
            selected = [copy.deepcopy(entries[value]) for value in entry_ids]
            for entry in selected:
                if entry["blocked_reason"]:
                    raise SteamCleanerError(entry["blocked_reason"])
            self._check_sources()
            activity = self._activity()
            mounts = filesystem.mount_points()
            targets = {}
            for entry in selected:
                reason = self._activity_reason(entry, activity)
                if reason:
                    raise SteamCleanerError(reason)
                target = self._targets[entry["id"]]
                current = filesystem.inspect_tree(target["path"], mounts, self._cancelled)
                if filesystem.tree_summary(current) != target["tree"]:
                    raise SteamCleanerError("path_changed")
                targets[entry["id"]] = target
            plan = {
                "id": grouped_id(), "scan_id": scan_id, "entries": selected,
                "estimated_bytes": sum(entry["bytes"] or 0 for entry in selected),
                "requires_prefix_confirmation": any(entry["kind"] == "compatdata" for entry in selected),
                "expires_at": time.time() + 300,
            }
            if self._cancelled.is_set():
                raise SteamCleanerError("cancelled")
            with self._state_lock:
                self._plans = {plan["id"]: {"public": plan, "targets": targets, "deadline": time.monotonic() + 300}}
            self._event("prepared", operation_id, "prepare", scan_id=scan_id, plan_id=plan["id"], count=len(selected))
            return copy.deepcopy(plan)

    def execute(self, plan_id, confirm_compatdata=False):
        with self._operation("execute") as operation_id:
            with self._state_lock:
                stored = self._plans.get(plan_id) if isinstance(plan_id, str) else None
                if stored is None:
                    raise SteamCleanerError("invalid_plan")
                if time.monotonic() >= stored["deadline"]:
                    self._plans.pop(plan_id, None)
                    raise SteamCleanerError("expired_plan")
                if stored["public"]["requires_prefix_confirmation"] and confirm_compatdata is not True:
                    raise SteamCleanerError("prefix_confirmation_required")
                self._plans.pop(plan_id)
                entries = stored["public"]["entries"]
                self._state.update(status="cleaning", error=None, progress={"processed": 0, "total": len(entries)})
            result = {"operation_id": operation_id, "items": [], "estimated_bytes_removed": 0, "cancelled": False}
            for entry in entries:
                item = {"id": entry["id"], "status": "skipped", "reason": None, "bytes_removed": 0, "entry": {key: entry[key] for key in ("appid", "name", "kind", "library_label", "library_internal")}}
                started_delete = False
                system_code = None
                try:
                    if self._cancelled.is_set():
                        raise SteamCleanerError("cancelled")
                    self._check_sources()
                    reason = self._activity_reason(entry, self._activity())
                    if reason:
                        raise SteamCleanerError(reason)
                    if self._cancelled.is_set():
                        raise SteamCleanerError("cancelled")
                    target = stored["targets"][entry["id"]]
                    mounts = filesystem.mount_points()
                    current = filesystem.inspect_tree(target["path"], mounts, self._cancelled)
                    if filesystem.tree_summary(current) != target["tree"]:
                        raise SteamCleanerError("path_changed")
                    reason = self._activity_reason(entry, self._activity())
                    if reason:
                        raise SteamCleanerError(reason)
                    self._check_sources()
                    if self._cancelled.is_set():
                        raise SteamCleanerError("cancelled")
                    started_delete = True
                    filesystem.remove_tree(target["path"], current, mounts)
                    item.update(status="deleted", bytes_removed=entry["bytes"] or 0)
                except (SteamCleanerError, filesystem.UnsafePath) as error:
                    item.update(status="error" if started_delete else "skipped", reason=error.code)
                    if isinstance(error, filesystem.DeletionError):
                        if error.changed:
                            item["reason"] = "partial_delete"
                        item["bytes_removed"] = error.bytes_removed
                        system_code = system_error(error)
                except OSError as error:
                    system_code = system_error(error)
                    item.update(status="error" if started_delete else "skipped", reason="io_error" if started_delete else "path_changed")
                result["estimated_bytes_removed"] += item["bytes_removed"]
                result["items"].append(item)
                result["cancelled"] = result["cancelled"] or item["reason"] == "cancelled"
                self._event(item["status"], operation_id, "execute", entry_id=entry["id"], library_id=entry["library_id"], appid=entry["appid"], kind=entry["kind"], reason=item["reason"], system_error=system_code, readback="absent" if item["status"] == "deleted" else "unverified")
                with self._state_lock:
                    self._state["progress"]["processed"] = len(result["items"])
                    self._state["last_result"] = copy.deepcopy(result)
            result["cancelled"] = result["cancelled"] or self._cancelled.is_set()
            with self._state_lock:
                outcomes = {item["id"]: item for item in result["items"]}
                self._state["entries"] = [entry for entry in self._state["entries"] if outcomes.get(entry["id"], {}).get("status") != "deleted"]
                for entry in self._state["entries"]:
                    if outcomes.get(entry["id"], {}).get("status") == "error":
                        entry.update(bytes=None, blocked_reason="path_changed")
                totals = {kind: sum(entry["bytes"] or 0 for entry in self._state["entries"] if entry["kind"] == kind) for kind in KINDS}
                totals["unknown"] = sum(entry["bytes"] is None for entry in self._state["entries"])
                self._state.update(status="cancelled" if result["cancelled"] else "ready", last_result=result, scan_id=None, totals=totals)
                self._plans.clear()
            self._event("completed", operation_id, "execute", plan_id=plan_id, scan_id=stored["public"]["scan_id"], count=len(result["items"]))
            return copy.deepcopy(result)

    def _entry(self, path, appid, kind, library, reason=None):
        return {
            "id": opaque(library["id"], kind, path.name), "game_id": f"app:{appid}" if appid != "unknown" else opaque(path),
            "appid": appid, "name": None, "kind": kind,
            "library_id": library["id"], "library_label": library["label"],
            "library_internal": library["internal"],
            "bytes": None, "installation": "unknown", "blocked_reason": reason,
            "requires_manual_selection": False,
            "warnings": ["prefix_data"] if kind == "compatdata" else [],
        }

    def _discover(self):
        roots = []
        complete = True
        for relative in (".local/share/Steam", ".steam/steam", ".steam/root"):
            candidate = self._home / relative
            if not os.path.lexists(candidate):
                continue
            source, root = filesystem.resolve_library_root(candidate)
            if root is None:
                complete = False
                continue
            if source != root:
                self._library_resolutions[str(source)] = root
            if root not in roots:
                roots.append(root)
        for root in list(roots):
            index = root / "steamapps/libraryfolders.vdf"
            try:
                self._remember(index)
                document = vdf.read_text(index).get("libraryfolders")
                if not isinstance(document, dict):
                    raise ValueError("malformed_vdf")
                for key, value in document.items():
                    if not key.isdecimal():
                        continue
                    raw = value.get("path") if isinstance(value, dict) else value
                    if not isinstance(raw, str) or not os.path.isabs(raw) or "\0" in raw:
                        raise ValueError("malformed_vdf")
                    source, path = filesystem.resolve_library_root(raw)
                    if path is None:
                        path = source
                    elif source != path:
                        self._library_resolutions[str(source)] = path
                    if path not in roots:
                        roots.append(path)
            except (OSError, ValueError, UnicodeError) as error:
                complete = False
                self._scan_issue("library_index", "coverage_incomplete", error, opaque(root))
        return roots, complete

    def _read_manifests(self, root, identities):
        complete = True
        try:
            with os.scandir(root / "steamapps") as entries:
                paths = sorted(Path(entry.path) for entry in entries if entry.name.startswith("appmanifest_") and entry.name.endswith(".acf"))
        except OSError as error:
            self._scan_issue("manifest", "coverage_incomplete", error, opaque(root))
            return False
        for path in paths:
            self._remember(path)
            try:
                document = vdf.read_text(path)
                if not document:
                    raise ValueError("empty")
                state = document.get("appstate")
                if not isinstance(state, dict):
                    raise ValueError("malformed_vdf")
                appid = state.get("appid")
                if not isinstance(appid, str) or not appid.isdecimal() or path.name != f"appmanifest_{appid}.acf":
                    raise ValueError("appid_mismatch")
                name = clean_name(state.get("name", ""))
                directory = state.get("installdir", "")
                runtime = False
                if isinstance(directory, str) and directory and "/" not in directory and directory not in (".", ".."):
                    marker = root / "steamapps/common" / directory / "toolmanifest.vdf"
                    self._remember(marker)
                    runtime = marker.exists()
                identities[appid] = {"name": name, "installation": "installed", "runtime": runtime or str(state.get("type", "")).lower() == "tool"}
            except (OSError, ValueError, UnicodeError) as error:
                vdf_error = "unicode" if isinstance(error, UnicodeError) else str(error) if isinstance(error, ValueError) else None
                # Steam names each manifest after its own AppID, so an unreadable file
                # leaves only that game unknown. A readable manifest that names another
                # game cannot be trusted for any AppID.
                owner = re.fullmatch(r"appmanifest_([0-9]{1,10})\.acf", path.name)
                if owner and vdf_error in VDF_ERRORS - {"appid_mismatch"}:
                    identities[owner.group(1)] = {"name": None, "installation": "unknown", "runtime": False}
                else:
                    complete = False
                self._scan_issue("manifest", "coverage_incomplete", error, opaque(root), vdf_error=vdf_error if vdf_error in VDF_ERRORS else None)
        return complete

    def _read_shortcuts(self, root, identities):
        userdata = root / "userdata"
        try:
            self._remember(userdata)
            if not userdata.exists():
                return True
            profiles = sorted(userdata.iterdir())
        except OSError as error:
            self._scan_issue("shortcuts", "coverage_incomplete", error, opaque(root))
            return False
        complete = True
        for profile in profiles:
            if not profile.name.isdecimal():
                continue
            path = profile / "config/shortcuts.vdf"
            try:
                self._remember(path)
                if not path.exists():
                    continue
                shortcuts = vdf.read_shortcuts(path)
                if not isinstance(shortcuts, dict):
                    raise ValueError("malformed_vdf")
                validated = []
                for value in shortcuts.values():
                    if not isinstance(value, dict) or not isinstance(value.get("appid"), int):
                        raise ValueError("malformed_vdf")
                    appid = str(value["appid"] & 0xFFFFFFFF)
                    name = clean_name(value.get("appname", ""))
                    validated.append((appid, name))
                for appid, name in validated:
                    previous = identities.get(appid)
                    if previous and (previous["installation"] == "unknown" or previous["name"] != name):
                        identities[appid] = {"name": None, "installation": "unknown", "runtime": previous.get("runtime", False)}
                    else:
                        identities[appid] = {"name": name, "installation": "non_steam"}
            except (OSError, ValueError, UnicodeError) as error:
                complete = False
                self._scan_issue("shortcuts", "coverage_incomplete", error, opaque(root))
        return complete

    def _remember(self, path):
        try:
            self._sources[str(path)] = filesystem.fingerprint(path.stat())
        except FileNotFoundError:
            self._sources[str(path)] = None

    def _check_sources(self):
        if not filesystem.library_resolutions_match(self._library_resolutions):
            raise SteamCleanerError("path_changed")
        for path, expected in self._sources.items():
            try:
                current = filesystem.fingerprint(os.stat(path))
            except FileNotFoundError:
                current = None
            if current != expected:
                raise SteamCleanerError("path_changed")

    def _activity(self):
        try:
            result = self._activity_provider()
            if not isinstance(result, dict) or result.get("complete") is not True or not isinstance(result.get("appids"), (list, set, tuple)) or not isinstance(result.get("paths"), (list, set, tuple)):
                return {"complete": False, "appids": [], "paths": []}
            if any(not str(value).isdecimal() for value in result["appids"]) or any(not isinstance(value, str) or not os.path.isabs(value) for value in result["paths"]):
                return {"complete": False, "appids": [], "paths": []}
            return {"complete": True, "appids": {str(value) for value in result["appids"]}, "paths": result["paths"]}
        except Exception:
            return {"complete": False, "appids": [], "paths": []}

    def _activity_reason(self, entry, activity):
        if not activity["complete"]:
            return "activity_unknown"
        if entry["appid"] in activity["appids"]:
            return "active_game"
        for library in self._libraries:
            try:
                (library / "steamapps/downloading" / entry["appid"]).lstat()
                return "active_download"
            except FileNotFoundError:
                pass
            except OSError:
                return "activity_unknown"
        target = self._targets.get(entry["id"])
        if target:
            for active in activity["paths"]:
                path = str(target["path"])
                if active == path or active.startswith(path + os.sep) or path.startswith(active.rstrip(os.sep) + os.sep):
                    return "active_game"
        return None

    def _internal_library(self, root, mounts):
        home = self._home.resolve()
        return root.is_relative_to(home) and not any(
            Path(mount) != home and Path(mount).is_relative_to(home) and root.is_relative_to(mount)
            for mount in mounts
        )

    def _library_label(self, root, mounts, index):
        containing = [mount for mount in mounts if mount != "/" and (str(root) == mount or str(root).startswith(mount + os.sep))]
        name = Path(max(containing, key=len)).name if containing else root.name
        if name == self._home.name or name in ("", ".", "/", "home", "Users", "root"):
            return f"Steam {index + 1}"
        return clean_name(name) or f"Steam {index + 1}"

    def _scan_issue(self, source, reason, error=None, library_id=None, appid=None, vdf_error=None):
        cause = "malformed_data" if isinstance(error, (ValueError, UnicodeError)) else system_error(error) if error else None
        key = (source, reason, cause, vdf_error)
        if key in self._scan_reported or len(self._scan_reported) >= 60:
            return
        self._scan_reported.add(key)
        self._event("error", self._diagnostic["last_operation_id"], "scan", source=source, reason=reason, system_error=cause, library_id=library_id, appid=appid, vdf_error=vdf_error)

    def _event(self, event, operation_id, phase, **fields):
        item = {"time": int(time.time()), "operation_id": operation_id, "phase": phase, "event": event}
        item.update({key: value for key, value in fields.items() if value is not None})
        with self._state_lock:
            self._diagnostic["events"] = (self._diagnostic["events"] + [item])[-120:]
        if self._logger:
            try:
                self._logger.info("steam_cleaner " + json.dumps(item, separators=(",", ":")))
            except Exception:
                pass
        self._save_history()

    def _load_history(self):
        if self._state_dir is None:
            return
        try:
            with open(self._state_dir / "steam_cleaner_history.json", "rb") as source:
                raw = source.read(128 * 1024 + 1)
            if len(raw) > 128 * 1024:
                raise ValueError("oversized_history")
            document = json.loads(raw)
            if not isinstance(document, dict) or document.get("schema_version") != 1:
                raise ValueError("invalid_history")
            events = document.get("events")
            if not isinstance(events, list):
                raise ValueError("invalid_history")
            allowed = []
            for item in events[-120:]:
                if not isinstance(item, dict) or item.get("event") not in EVENTS or item.get("phase") not in PHASES or not isinstance(item.get("operation_id"), str) or not re.fullmatch(r"(?:[a-f0-9]{4}-){7}[a-f0-9]{4}", item["operation_id"]) or type(item.get("time")) is not int:
                    self._diagnostic["persistence_error"] = "io_error"
                    continue
                result = {key: item[key] for key in ("event", "phase", "operation_id", "time")}
                for key in ("scan_id", "plan_id"):
                    if isinstance(item.get(key), str) and re.fullmatch(r"(?:[a-f0-9]{4}-){7}[a-f0-9]{4}", item[key]):
                        result[key] = item[key]
                for key in ("entry_id", "library_id"):
                    if isinstance(item.get(key), str) and re.fullmatch(r"(?:[a-f0-9]{4}-){5}[a-f0-9]{4}", item[key]):
                        result[key] = item[key]
                if isinstance(item.get("appid"), str) and re.fullmatch(r"[0-9]{1,10}", item["appid"]):
                    result["appid"] = item["appid"]
                for key in ("reason", "system_error"):
                    if item.get(key) in REASONS:
                        result[key] = item[key]
                if item.get("kind") in KINDS:
                    result["kind"] = item["kind"]
                if item.get("source") in SOURCES:
                    result["source"] = item["source"]
                if item.get("vdf_error") in VDF_ERRORS:
                    result["vdf_error"] = item["vdf_error"]
                if item.get("readback") in ("absent", "unverified"):
                    result["readback"] = item["readback"]
                for key in ("count", "duration_ms"):
                    if type(item.get(key)) is int and 0 <= item[key] <= 10**12:
                        result[key] = item[key]
                allowed.append(result)
            self._diagnostic["events"] = allowed
            if allowed:
                self._diagnostic["last_operation_id"] = allowed[-1]["operation_id"]
            self._diagnostic["interrupted"] = document.get("phase") in ("scan", "prepare", "execute") or document.get("interrupted") is True
            if document.get("phase") in ("scan", "prepare", "execute"):
                self._diagnostic["events"] = (allowed + [{"time": int(time.time()), "operation_id": self._diagnostic["last_operation_id"] or grouped_id(), "phase": "idle", "event": "interrupted"}])[-120:]
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError):
            self._diagnostic["persistence_error"] = "io_error"

    def _save_history(self):
        if self._state_dir is None:
            return
        temporary = None
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            temporary = self._state_dir / f".steam_cleaner_{uuid.uuid4().hex}.tmp"
            with open(temporary, "x", encoding="utf-8") as output:
                with self._state_lock:
                    document = copy.deepcopy(self._diagnostic)
                json.dump(document, output, separators=(",", ":"))
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self._state_dir / "steam_cleaner_history.json")
            with self._state_lock:
                self._diagnostic["persistence_error"] = None
        except OSError:
            with self._state_lock:
                self._diagnostic["persistence_error"] = "io_error"
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
