import copy
import json
import os
import re
import stat
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import filesystem, vdf
from .activity import process_activity
from .service import REASONS, SteamCleanerError, clean_name, grouped_id, opaque, system_error


PLAN_LIFETIME_SECONDS = 300
EVENTS = {"started", "completed", "prepared", "deleted", "skipped", "error", "interrupted"}
PHASES = {"idle", "scan", "prepare", "execute"}
ID_PATTERN = re.compile(r"(?:[a-f0-9]{4}-){7}[a-f0-9]{4}")
OPAQUE_PATTERN = re.compile(r"(?:[a-f0-9]{4}-){5}[a-f0-9]{4}")


def _walk_values(value):
    if not isinstance(value, dict):
        return
    yield value
    for child in value.values():
        yield from _walk_values(child)


def _compat_references(document):
    names = set()
    for value in _walk_values(document):
        mapping = value.get("compattoolmapping")
        if not isinstance(mapping, dict):
            continue
        for selection in mapping.values():
            if isinstance(selection, dict) and isinstance(selection.get("name"), str):
                name = selection["name"].strip()
                if name:
                    names.add(name.casefold())
    return names


def _custom_tool_names(document):
    for value in _walk_values(document):
        tools = value.get("compat_tools")
        if isinstance(tools, dict):
            result = []
            for name, details in tools.items():
                if not isinstance(name, str) or not name.strip():
                    continue
                display = details.get("display_name") if isinstance(details, dict) else None
                result.append((name, display.strip() if isinstance(display, str) and display.strip() else name))
            return result
    return []


class ProtonCleanerService:
    def __init__(self, home, logger=None, state_dir=None, activity_provider=None):
        self._home = Path(home)
        self._logger = logger
        self._state_dir = Path(state_dir) if state_dir is not None else None
        self._activity_provider = activity_provider or self._process_activity
        self._lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._cancelled = threading.Event()
        self._closed = False
        self._targets = {}
        self._sources = {}
        self._plans = {}
        self._libraries = []
        self._state = {
            "schema_version": 1,
            "available": False,
            "status": "idle",
            "scan_id": None,
            "coverage_complete": False,
            "entries": [],
            "totals": {"bytes": 0, "unknown": 0},
            "progress": {"processed": 0, "total": None},
            "error": None,
            "last_result": None,
        }
        self._diagnostic = {
            "schema_version": 1, "phase": "idle", "last_operation_id": None,
            "interrupted": False, "events": [], "persistence_error": None,
        }
        self._load_history()

    def get_state(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def diagnostics(self):
        with self._lock:
            return copy.deepcopy(self._diagnostic)

    def cancel(self):
        self._cancelled.set()
        with self._lock:
            self._plans.clear()
        return self.get_state()

    def close(self):
        with self._lock:
            self._closed = True
            self._cancelled.set()
            self._plans.clear()
        with self._operation_lock:
            pass
        self._save_history()

    @contextmanager
    def _operation(self, phase):
        if not self._operation_lock.acquire(blocking=False):
            raise SteamCleanerError("busy")
        operation_id = grouped_id()
        try:
            with self._lock:
                if self._closed:
                    raise SteamCleanerError("closed")
                self._cancelled.clear()
                self._diagnostic["phase"] = phase
                self._diagnostic["last_operation_id"] = operation_id
            self._event("started", operation_id, phase)
            yield operation_id
        except SteamCleanerError as error:
            self._event("error", operation_id, phase, reason=error.code)
            raise
        except (OSError, ValueError, filesystem.UnsafePath) as error:
            code = getattr(error, "code", "io_error")
            with self._lock:
                self._state.update(status="error", error=code)
            details = {"reason": code}
            if isinstance(error, OSError) or getattr(error, "errno", None) is not None:
                details["system_error"] = system_error(error)
            self._event("error", operation_id, phase, **details)
            raise SteamCleanerError(code) from None
        except Exception:
            with self._lock:
                self._state.update(status="error", error="internal_error")
            self._event("error", operation_id, phase, reason="internal_error")
            raise SteamCleanerError("internal_error") from None
        finally:
            with self._lock:
                self._diagnostic["phase"] = "idle"
            self._save_history()
            self._operation_lock.release()

    def inventory(self):
        with self._operation("scan") as operation_id:
            with self._lock:
                self._plans.clear()
                self._state.update(status="scanning", scan_id=None, error=None, progress={"processed": 0, "total": None})
            self._targets = {}
            self._sources = {}
            roots, complete = self._discover()
            self._libraries = roots
            references, references_complete = self._read_references(roots)
            complete = complete and references_complete
            mounts = filesystem.mount_points()
            activity = self._activity()
            entries = []
            for root in roots:
                official, official_complete = self._official_entries(root, mounts)
                entries.extend(official)
                complete = complete and official_complete
                custom, custom_complete = self._custom_entries(root, mounts, references, complete, activity)
                entries.extend(custom)
                complete = complete and custom_complete
                with self._lock:
                    self._state["progress"]["processed"] = len(entries)
                if self._cancelled.is_set():
                    complete = False
                    break
            total = sum(entry["bytes"] or 0 for entry in entries)
            state = {
                "available": bool(roots),
                "status": "cancelled" if self._cancelled.is_set() else "ready",
                "scan_id": grouped_id() if not self._cancelled.is_set() else None,
                "coverage_complete": complete,
                "entries": entries,
                "totals": {"bytes": total, "unknown": sum(entry["bytes"] is None for entry in entries)},
                "progress": {"processed": len(entries), "total": len(entries)},
                "error": None,
            }
            with self._lock:
                self._state.update(state)
            self._event("completed", operation_id, "scan", count=len(entries), complete=complete)
            return self.get_state()

    def prepare(self, scan_id, entry_ids):
        with self._operation("prepare") as operation_id:
            if not isinstance(scan_id, str) or not isinstance(entry_ids, list) or not entry_ids or any(not isinstance(value, str) for value in entry_ids) or len(set(entry_ids)) != len(entry_ids):
                raise SteamCleanerError("invalid_selection")
            with self._lock:
                if scan_id != self._state["scan_id"]:
                    raise SteamCleanerError("stale_scan")
                entries = {entry["id"]: entry for entry in self._state["entries"]}
            selected = []
            for entry_id in entry_ids:
                entry = entries.get(entry_id)
                if not entry:
                    raise SteamCleanerError("invalid_selection")
                if not entry["selectable"]:
                    raise SteamCleanerError("tool_in_use" if entry["status"] == "in_use" else "protected_tool")
                selected.append(entry)
            self._check_sources()
            activity = self._activity()
            if not activity["complete"]:
                raise SteamCleanerError("activity_unknown")
            mounts = filesystem.mount_points()
            reviewed = {}
            for entry in selected:
                target = self._targets.get(entry["id"])
                if not target:
                    raise SteamCleanerError("invalid_selection")
                if self._path_active(str(target["path"]), activity["paths"]):
                    raise SteamCleanerError("active_game")
                tree = filesystem.inspect_tree(target["path"], mounts, self._cancelled)
                if filesystem.tree_summary(tree) != target["tree"]:
                    raise SteamCleanerError("path_changed")
                reviewed[entry["id"]] = {"path": target["path"], "tree": tree}
            plan_id = grouped_id()
            public = {
                "id": plan_id,
                "scan_id": scan_id,
                "entries": copy.deepcopy(selected),
                "estimated_bytes": sum(entry["bytes"] or 0 for entry in selected),
                "expires_at": time.time() + PLAN_LIFETIME_SECONDS,
            }
            with self._lock:
                self._plans = {plan_id: {"public": public, "reviewed": reviewed, "created": time.monotonic()}}
            self._event("prepared", operation_id, "prepare", count=len(selected))
            return copy.deepcopy(public)

    def execute(self, plan_id):
        with self._operation("execute") as operation_id:
            with self._lock:
                stored = self._plans.pop(plan_id, None) if isinstance(plan_id, str) else None
            if not stored:
                raise SteamCleanerError("invalid_plan")
            if time.monotonic() - stored["created"] > PLAN_LIFETIME_SECONDS:
                raise SteamCleanerError("expired_plan")
            self._check_sources()
            mounts = filesystem.mount_points()
            result = {"operation_id": operation_id, "items": [], "estimated_bytes_removed": 0, "cancelled": False}
            for entry in stored["public"]["entries"]:
                item = {"id": entry["id"], "status": "error", "reason": None, "bytes_removed": 0}
                reviewed = stored["reviewed"][entry["id"]]
                started_delete = False
                system_code = None
                try:
                    if self._cancelled.is_set():
                        item.update(status="skipped", reason="cancelled")
                        result["cancelled"] = True
                    else:
                        activity = self._activity()
                        if not activity["complete"]:
                            item.update(status="skipped", reason="activity_unknown")
                        elif self._path_active(str(reviewed["path"]), activity["paths"]):
                            item.update(status="skipped", reason="active_game")
                        else:
                            tree = filesystem.inspect_tree(reviewed["path"], mounts, self._cancelled)
                            if filesystem.tree_summary(tree) != filesystem.tree_summary(reviewed["tree"]):
                                raise filesystem.UnsafePath("path_changed")
                            self._check_sources()
                            activity = self._activity()
                            if self._cancelled.is_set():
                                item.update(status="skipped", reason="cancelled")
                                result["cancelled"] = True
                            elif not activity["complete"]:
                                item.update(status="skipped", reason="activity_unknown")
                            elif self._path_active(str(reviewed["path"]), activity["paths"]):
                                item.update(status="skipped", reason="active_game")
                            else:
                                started_delete = True
                                filesystem.remove_tree(reviewed["path"], reviewed["tree"], mounts)
                                item.update(status="deleted", bytes_removed=entry["bytes"] or 0)
                except (OSError, filesystem.UnsafePath, SteamCleanerError) as error:
                    item["status"] = "error" if started_delete else "skipped"
                    item["reason"] = getattr(error, "code", "io_error")
                    if isinstance(error, filesystem.DeletionError):
                        item["bytes_removed"] = error.bytes_removed
                        if error.changed:
                            item["reason"] = "partial_delete"
                    if isinstance(error, OSError) or getattr(error, "errno", None) is not None:
                        system_code = system_error(error)
                    if item["reason"] == "cancelled":
                        result["cancelled"] = True
                result["estimated_bytes_removed"] += item["bytes_removed"]
                result["items"].append(item)
                self._event(
                    item["status"], operation_id, "execute", entry_id=entry["id"],
                    reason=item["reason"], system_error=system_code,
                    readback="absent" if item["status"] == "deleted" else "unverified",
                )
            deleted = {item["id"] for item in result["items"] if item["status"] == "deleted"}
            with self._lock:
                self._state["entries"] = [entry for entry in self._state["entries"] if entry["id"] not in deleted]
                self._state.update(status="cancelled" if result["cancelled"] else "ready", scan_id=None, last_result=copy.deepcopy(result))
                self._state["totals"] = {
                    "bytes": sum(entry["bytes"] or 0 for entry in self._state["entries"]),
                    "unknown": sum(entry["bytes"] is None for entry in self._state["entries"]),
                }
                self._plans.clear()
            self._event("completed", operation_id, "execute", count=len(result["items"]))
            return result

    def _discover(self):
        roots = []
        aliases = {}
        complete = True
        for relative in (".local/share/Steam", ".steam/steam", ".steam/root"):
            candidate = self._home / relative
            if not os.path.lexists(candidate):
                continue
            try:
                root = candidate.resolve(strict=True)
                aliases[str(candidate)] = root
                if root not in roots:
                    roots.append(root)
            except (OSError, RuntimeError):
                complete = False
        for root in list(roots):
            index = root / "steamapps/libraryfolders.vdf"
            try:
                self._remember(index)
                libraries = vdf.read_text(index).get("libraryfolders")
                if not isinstance(libraries, dict):
                    raise ValueError("malformed_vdf")
                for key, value in libraries.items():
                    if not key.isdecimal():
                        continue
                    raw = value.get("path") if isinstance(value, dict) else value
                    if not isinstance(raw, str) or not os.path.isabs(raw) or "\0" in raw:
                        raise ValueError("malformed_vdf")
                    path = aliases.get(os.path.abspath(raw), Path(os.path.abspath(raw)))
                    if path not in roots:
                        roots.append(path)
            except (OSError, ValueError, UnicodeError):
                complete = False
        return roots, complete

    def _read_references(self, roots):
        references = set()
        complete = True
        paths = []
        for root in roots:
            paths.append(root / "config/config.vdf")
            userdata = root / "userdata"
            self._remember(userdata)
            try:
                paths.extend(profile / "config/localconfig.vdf" for profile in userdata.iterdir() if profile.name.isdecimal())
            except FileNotFoundError:
                pass
            except OSError:
                complete = False
        for path in paths:
            self._remember(path)
            if not path.exists():
                continue
            try:
                references.update(_compat_references(vdf.read_text(path)))
            except (OSError, ValueError, UnicodeError):
                complete = False
        return references, complete

    def _official_entries(self, root, mounts):
        entries = []
        complete = True
        steamapps = root / "steamapps"
        try:
            manifests = sorted(path for path in steamapps.iterdir() if path.name.startswith("appmanifest_") and path.name.endswith(".acf"))
        except OSError:
            return entries, False
        for manifest in manifests:
            self._remember(manifest)
            try:
                state = vdf.read_text(manifest).get("appstate")
                if not isinstance(state, dict):
                    complete = False
                    continue
                appid = state.get("appid")
                name = clean_name(state.get("name", ""))
                directory = state.get("installdir")
                kind = state.get("type")
                if not isinstance(appid, str) or not appid.isdecimal() or not name or not isinstance(directory, str) or "/" in directory or directory in ("", ".", ".."):
                    complete = False
                    continue
                lower = name.casefold()
                if "proton" not in lower and "steam linux runtime" not in lower:
                    continue
                path = steamapps / "common" / directory
                if kind is not None:
                    if not isinstance(kind, str):
                        complete = False
                        continue
                    if kind.casefold() != "tool":
                        continue
                else:
                    try:
                        marker = (path / "toolmanifest.vdf").lstat()
                    except FileNotFoundError:
                        continue
                    except OSError:
                        complete = False
                        continue
                    if not stat.S_ISREG(marker.st_mode):
                        continue
                size = None
                try:
                    size = filesystem.inspect_tree(path, mounts, self._cancelled)["bytes"]
                except (OSError, filesystem.UnsafePath):
                    complete = False
                protected = "steam linux runtime" in lower
                entries.append({
                    "id": opaque("official", appid), "name": name, "tool_name": directory,
                    "source": "steam", "appid": appid, "bytes": size,
                    "status": "protected" if protected else "managed_by_steam",
                    "selectable": False, "recommended": False,
                    "reason": "runtime" if protected else "managed_by_steam",
                })
            except (OSError, ValueError, UnicodeError):
                complete = False
        return entries, complete

    def _custom_entries(self, root, mounts, references, coverage_complete, activity):
        custom_root = root / "compatibilitytools.d"
        self._remember(custom_root)
        try:
            children = sorted(custom_root.iterdir(), key=lambda path: path.name.casefold())
        except FileNotFoundError:
            return [], True
        except OSError:
            return [], False
        entries = []
        complete = True
        for path in children:
            reason = None
            names = []
            tree = None
            try:
                value = path.lstat()
                if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
                    raise filesystem.UnsafePath("unsafe_path")
                manifest = path / "compatibilitytool.vdf"
                self._remember(manifest)
                names = _custom_tool_names(vdf.read_text(manifest))
                if not names:
                    raise ValueError("malformed_data")
                if not any("proton" in name.casefold() or "proton" in display.casefold() for name, display in names):
                    continue
                tree = filesystem.inspect_tree(path, mounts, self._cancelled)
            except (OSError, ValueError, UnicodeError, filesystem.UnsafePath) as error:
                complete = False
                reason = getattr(error, "code", reason or "malformed_data")
                if not names:
                    continue
            display = clean_name(names[0][1] if names else path.name) or "Proton personalizado"
            referenced = any(name.casefold() in references for name, _ in names)
            if reason:
                status = "protected"
            elif not coverage_complete:
                status, reason = "protected", "coverage_incomplete"
            elif referenced:
                status, reason = "in_use", "tool_in_use"
            elif not activity["complete"]:
                status, reason = "protected", "activity_unknown"
            elif self._path_active(str(path), activity["paths"]):
                status, reason = "in_use", "active_game"
            else:
                status = "unused"
            entry = {
                "id": opaque("custom", path), "name": display, "tool_name": names[0][0] if names else path.name,
                "source": "custom", "appid": None, "bytes": tree["bytes"] if tree else None,
                "status": status, "selectable": status == "unused", "recommended": status == "unused",
                "reason": reason,
            }
            entries.append(entry)
            if tree:
                self._targets[entry["id"]] = {"path": path, "tree": filesystem.tree_summary(tree)}
        return entries, complete

    def _process_activity(self):
        roots = [str(root / "compatibilitytools.d") for root in self._libraries]
        roots.extend(str(target["path"]) for target in self._targets.values())
        return process_activity(self._home, data_roots=roots)

    def _activity(self):
        try:
            result = self._activity_provider()
            if not isinstance(result, dict) or result.get("complete") is not True or not isinstance(result.get("paths"), (list, tuple, set)):
                return {"complete": False, "paths": []}
            paths = result["paths"]
            if any(not isinstance(path, str) or not os.path.isabs(path) for path in paths):
                return {"complete": False, "paths": []}
            return {"complete": True, "paths": list(paths)}
        except Exception:
            return {"complete": False, "paths": []}

    @staticmethod
    def _path_active(path, active_paths):
        return any(active == path or active.startswith(path + os.sep) or path.startswith(active.rstrip(os.sep) + os.sep) for active in active_paths)

    def _remember(self, path):
        try:
            self._sources[str(path)] = filesystem.fingerprint(path.stat())
        except FileNotFoundError:
            self._sources[str(path)] = None

    def _check_sources(self):
        for path, expected in self._sources.items():
            try:
                current = filesystem.fingerprint(os.stat(path))
            except FileNotFoundError:
                current = None
            if current != expected:
                raise SteamCleanerError("path_changed")

    def _event(self, event, operation_id, phase, **details):
        item = {"event": event, "operation_id": operation_id, "phase": phase, "at": int(time.time()), **details}
        with self._lock:
            self._diagnostic["events"] = (self._diagnostic["events"] + [item])[-80:]
        if self._logger:
            try:
                self._logger.info("proton_cleaner " + json.dumps(item, separators=(",", ":")))
            except Exception:
                pass
        self._save_history()

    def _load_history(self):
        if self._state_dir is None:
            return
        try:
            with open(self._state_dir / "proton_cleaner_history.json", "rb") as source:
                raw = source.read(64 * 1024 + 1)
            if len(raw) > 64 * 1024:
                raise ValueError("oversized_history")
            document = json.loads(raw)
            if not isinstance(document, dict) or document.get("schema_version") != 1 or not isinstance(document.get("events"), list):
                raise ValueError("invalid_history")
            allowed = []
            for item in document["events"][-80:]:
                if not isinstance(item, dict) or item.get("event") not in EVENTS or item.get("phase") not in PHASES or not isinstance(item.get("operation_id"), str) or not ID_PATTERN.fullmatch(item["operation_id"]) or type(item.get("at")) is not int:
                    self._diagnostic["persistence_error"] = "io_error"
                    continue
                event = {key: item[key] for key in ("event", "phase", "operation_id", "at")}
                if item.get("reason") in REASONS:
                    event["reason"] = item["reason"]
                if item.get("system_error") in REASONS:
                    event["system_error"] = item["system_error"]
                if isinstance(item.get("entry_id"), str) and OPAQUE_PATTERN.fullmatch(item["entry_id"]):
                    event["entry_id"] = item["entry_id"]
                if item.get("readback") in ("absent", "unverified"):
                    event["readback"] = item["readback"]
                if type(item.get("count")) is int and 0 <= item["count"] <= 10_000:
                    event["count"] = item["count"]
                if type(item.get("complete")) is bool:
                    event["complete"] = item["complete"]
                allowed.append(event)
            self._diagnostic["events"] = allowed
            if allowed:
                self._diagnostic["last_operation_id"] = allowed[-1]["operation_id"]
            if document.get("phase") in ("scan", "prepare", "execute") or document.get("interrupted") is True:
                self._diagnostic["interrupted"] = True
            if document.get("phase") in ("scan", "prepare", "execute"):
                self._diagnostic["events"] = (allowed + [{
                    "event": "interrupted", "operation_id": self._diagnostic["last_operation_id"] or grouped_id(),
                    "phase": "idle", "at": int(time.time()),
                }])[-80:]
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
            temporary = self._state_dir / f".proton_cleaner_{uuid.uuid4().hex}.tmp"
            with self._lock:
                document = copy.deepcopy(self._diagnostic)
            with open(temporary, "x", encoding="utf-8") as output:
                json.dump(document, output, separators=(",", ":"))
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self._state_dir / "proton_cleaner_history.json")
            with self._lock:
                self._diagnostic["persistence_error"] = None
        except OSError:
            with self._lock:
                self._diagnostic["persistence_error"] = "io_error"
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
