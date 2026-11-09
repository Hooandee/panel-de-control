"""Per-game OptiScaler installs: plan, apply with a hashed manifest, verify, undo."""

import copy
import hashlib
import json
import os
import shutil
import threading
import tempfile
import time
import uuid
from pathlib import Path

from json_store import atomic_json_save

from . import solution_plan, auto_recipes, prefix_dependencies, engine_updates, capture, catalog, diagnostics, games, helixsr, identify, image_settings, ini, keys, latest, launchers, launch_state, logread, lsfg, luma, mako, ownership, recipe_catalog, recipes, scaler_transition, user_deps, wiki
from .assets import AssetCache, AssetError, sha256

HISTORY_LIMIT = 20
_JUNK = {"setup_linux.sh", "setup_windows.bat"}
_ARCHIVE_DIRS = ("D3D12_Optiscaler",)
_GENERATED = ("OptiScaler.log",)
# REFramework opens its menu over the game on first launch unless its config says otherwise; handhelds have no
# Insert key to close it, so Panel seeds that config when the game has none. REFramework rewrites it later.
REFRAMEWORK_CONFIG = "re2_fw_config.txt"
REFRAMEWORK_CLOSED = {"REFrameworkConfig_RememberMenuState": "true", "REFrameworkConfig_MenuOpen": "false"}
_SEEDED = (REFRAMEWORK_CONFIG,)


def _with_keys(text: str, values: dict[str, str | None]) -> str:
    """REFramework's flat `key=value` config with these keys set (None removes one); every other line kept."""
    lines, seen = [], set()
    for line in text.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line else None
        if key in values:
            if key in seen or values[key] is None:
                continue
            seen.add(key)
            line = f"{key}={values[key]}"
        lines.append(line)
    lines += [f"{key}={value}" for key, value in values.items() if key not in seen and value is not None]
    return "\n".join(lines) + "\n"


def _keys(text: str, names) -> dict[str, str | None]:
    found: dict[str, str | None] = {name: None for name in names}
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key.strip() in found:
            found[key.strip()] = value.strip()
    return found
HELIX_MARKER = "helixsr.json"
# Proton's own FSR 4 switch: the official name and the per-GPU names custom builds keep.
PROTON_FSR4_ENVS = ("FSR4_UPGRADE", "PROTON_FSR4_UPGRADE", "PROTON_FSR4_RDNA3_UPGRADE")
# What HelixSR's bridge leaves in the game for each way; gone means a game update or verify removed it.
HELIX_INSTALL_FILE = "helixsr-install.json"


# Native Linux games run without Proton; OptiScaler only hooks Windows executables.
NATIVE_ANALYSIS = {
    "candidates": [], "exe": None, "apis": [], "manual": False, "target": None,
    "inputs": {}, "dll_targets": [], "anti_cheat": False, "foreign": False, "foreign_identity": None,
}


class UpscalerError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def panel_resolution(drm: str = "/sys/class/drm") -> list[int] | None:
    """Native mode of the built-in panel (first connected eDP/DSI/LVDS), else any connected output."""
    connected = []
    try:
        names = sorted(os.listdir(drm))
    except OSError:
        return None
    for name in names:
        base = os.path.join(drm, name)
        try:
            with open(os.path.join(base, "status")) as status, open(os.path.join(base, "modes")) as modes:
                if status.read().strip() != "connected":
                    continue
                width, _, height = modes.readline().strip().partition("x")
                mode = [int(width), int(height.rstrip("i"))]
        except (OSError, ValueError):
            continue
        connected.append((not any(kind in name for kind in ("eDP", "DSI", "LVDS")), mode))
    return sorted(connected)[0][1] if connected else None


def _overrides(install: dict) -> list[str]:
    """WINEDLLOVERRIDES entries Panel owns for an install: the proxy plus any recipe DLLs."""
    proxy = install.get("proxy", "dxgi.dll")
    names = [*([str(proxy).removesuffix(".dll")] if proxy else []), *install.get("native_dlls", [])]
    return [f"{name}=n,b" for name in dict.fromkeys(names)]


class UpscalerService:
    def __init__(self, home: str, state_dir: str, gpu: str, logger=None, proc: str = "/proc", drm: str = "/sys/class/drm", device: str = ""):
        self.home = home
        self.gpu = gpu
        self.device = device
        self.logger = logger
        self.proc = proc
        self.drm = drm
        self.search = identify.store_search
        self.press = keys.press
        self.state_path = Path(state_dir) / "state.json"
        self.cache = AssetCache(Path(state_dir) / "cache")
        self.latest = latest.Resolver(Path(state_dir), logger=logger)
        self._fallbacks: dict[str, str] = {}
        self.lsfg = lsfg.Lsfg(home, Path(state_dir))
        self.mako = mako.Mako(home, Path(state_dir))
        self._engine_lock = threading.RLock()
        self._image_lock = threading.RLock()
        self._engine_checks = {}
        self.engine_game_running = lambda: False
        self.launch_receipts = launch_state.LaunchReceipts(Path(state_dir))
        self.scaler_transitions = scaler_transition.Checkpoints(Path(state_dir))
        self.helix = helixsr.HelixSR(home)
        self.wiki = wiki.WikiCache(Path(state_dir))
        self.user_files = user_deps.Store(Path(state_dir) / "user-files")
        self._lock = threading.Lock()
        self._compat: dict[str, tuple[float, bool]] = {}
        self._job: dict | None = None
        self._cancel = threading.Event()
        self.state = self._load()

    # ---- persistence ---------------------------------------------------------
    def _load(self) -> dict:
        try:
            data = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            data = {}
        games_state = data.get("games") if isinstance(data, dict) else None
        if isinstance(games_state, dict):
            for entry in games_state.values():
                if not isinstance(entry, dict) or not isinstance(entry.get("history"), list):
                    continue
                for item in entry["history"]:
                    facts = item.get("facts") if isinstance(item, dict) else None
                    if isinstance(facts, dict) and "resolution" in facts and "resolution_source" not in facts:
                        # Older releases persisted initialization dimensions as current resolution.
                        facts.setdefault("initial_resolution", facts.pop("resolution"))
                        facts["resolution_source"] = "initialization_only"
        return {"games": games_state if isinstance(games_state, dict) else {},
                "global_actions": data.get("global_actions", [])[-20:] if isinstance(data, dict) and isinstance(data.get("global_actions"), list) else []}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_save(str(self.state_path), self.state)

    def _game_state(self, appid: str) -> dict:
        entry = self.state["games"].setdefault(appid, {})
        entry.setdefault("history", [])
        return entry

    def diagnostic_ini_request(self, appid: str, key: str, value: str) -> dict:
        try:
            _, path = self._ini_path(appid)
            return diagnostics.ini_request(path, key, value)
        except Exception:
            return {"key": str(key)[:120], "value_omitted": True}

    def record_action(self, appid: str, action: str, state: str, requested=None, error=None) -> None:
        try:
            self._record_action(appid, action, state, requested, error)
        except Exception:
            if self.logger:
                self.logger.warning("Upscaler diagnostic history could not be recorded")

    def _record_action(self, appid: str, action: str, state: str, requested=None, error=None) -> None:
        global_action = appid == "global"
        entry = {"actions": self.state.get("global_actions", [])} if global_action else self._game_state(str(appid))
        event = {"at": time.time(), "action": action[:60], "state": state,
                 "requested": diagnostics.fields(requested, diagnostics.REQUEST_KEYS)}
        if not global_action:
            event["snapshot"] = diagnostics.snapshot(entry.get("install"))
        if action == "lsfg_game":
            try:
                profile = self.lsfg.status().get("profiles", {}).get(str(appid))
                event["applied_lsfg"] = {"enabled": profile is not None,
                    **diagnostics.fields(profile, ("multiplier", "flow", "performance"))}
            except Exception:
                event["applied_lsfg"] = {"status": "unavailable"}
        if action == "mako_game":
            try:
                profile = self.mako_status(str(appid)).get("profiles", {}).get(str(appid))
                event["applied_mako"] = {"enabled": profile is not None,
                    **diagnostics.fields(profile, ("enabled", "mode", "multiplier", "target_fps", "max_multiplier", "flow", "performance", "scaling_enabled", "scaling_factor", "scaling_sharpness"))}
            except Exception:
                event["applied_mako"] = {"status": "unavailable"}
        job = self.job()
        if job and str(job.get("appid")) == str(appid):
            event["job_id"] = job.get("id")
        if error:
            event["error"] = str(error)[:80]
            if job and str(job.get("appid")) == str(appid) and job.get("detail"):
                detail = diagnostics.error_detail(job["detail"])
                if detail:
                    event["detail"] = detail
        entry["actions"] = [*(entry.get("actions") or []), event][-20:]
        if global_action:
            self.state["global_actions"] = entry["actions"]
        self._save()

    # ---- read side -----------------------------------------------------------
    def overview(self) -> dict:
        installs = {}
        for appid, entry in self.state["games"].items():
            install = entry.get("install")
            if isinstance(install, dict):
                installs[appid] = {
                    "build": install.get("build"),
                    "proxy": install.get("proxy"),
                    "status": self._status(install, entry),
                    "options": install.get("options") or {},
                }
        return {
            "gpu": self.gpu,
            "display": panel_resolution(self.drm),
            "preferred": catalog.preferred_build(self.gpu),
            "builds": catalog.describe(self.gpu, self.device),
            "cached": [a.id for a in catalog.ASSETS.values() if self.cache.ready(a)],
            "installs": installs,
            "engines": self._engine_summaries(),
            "job": self.job(),
            "helixsr": {"downloaded": self.helix.ready()},
        }

    def _engine_summaries(self) -> dict:
        """What Mako and Lossless Scaling do per game, for the list: neither shows up as an install."""
        summaries: dict[str, dict] = {}
        try:
            for key, profile in (self.mako.status().get("profiles") or {}).items():
                if isinstance(profile, dict):
                    summaries.setdefault(str(key), {})["mako"] = {
                        "spatial": bool(profile.get("scaling_enabled")), "fg": bool(profile.get("enabled")),
                        "multiplier": profile.get("multiplier") if type(profile.get("multiplier")) is int else None}
        except Exception as error:  # noqa: BLE001 — the list still shows every scaler install without it
            if self.logger:
                self.logger.info(f"Mako summary unavailable: {type(error).__name__}")
        try:
            for key, profile in (self.lsfg.status().get("profiles") or {}).items():
                if isinstance(profile, dict):
                    summaries.setdefault(str(key), {})["lossless"] = {
                        "multiplier": profile.get("multiplier") if type(profile.get("multiplier")) is int else None}
        except Exception as error:  # noqa: BLE001
            if self.logger:
                self.logger.info(f"Lossless summary unavailable: {type(error).__name__}")
        return summaries

    def _status(self, install: dict, entry: dict) -> str:
        target = Path(install.get("target", ""))
        if install.get("engine") == "dll":
            manifest = diagnostics._manifest_check(target)
            return "not_run" if manifest.get("present") and manifest.get("files") and not manifest.get("missing") and not manifest.get("changed") else "broken"
        if install.get("engine") == "proton":
            history = entry.get("history") or []
            return history[-1].get("result", "pending") if history else "pending"
        if install.get("engine") == "helixsr":
            ours = (target / games.MANIFEST_DIR / HELIX_MARKER).is_file()
            if not ours or not Path(install.get("helix_file", "")).is_file():
                return "broken"
            history = entry.get("history") or []
            return history[-1].get("result", "pending") if history else "pending"
        proxy = install.get("proxy") or ""
        if not (target / games.MANIFEST_DIR / "manifest.json").is_file() or not (target / proxy).is_file():
            return "broken"
        history = entry.get("history") or []
        return history[-1].get("result", "pending") if history else "pending"

    def compatibility(self, appids: list[str]) -> dict[str, dict]:
        """What each game ships (or that it runs natively on Linux), cached by install folder mtime."""
        result = {}
        for appid in appids[:400]:
            installed = self._find(str(appid))
            if installed is None:
                continue
            try:
                stamp = installed.root.stat().st_mtime
            except OSError:
                continue
            cached = self._compat.get(installed.appid)
            if cached is None or cached[0] != stamp:
                cached = (stamp, {"native": installed.native,
                                  "inputs": [] if installed.native else games.shipped_upscalers(installed.root)})
                self._compat[installed.appid] = cached
            try:
                automatic = auto_recipes.plan(recipes.recipe_for(installed.appid, game_build=installed.build_id), installed)
            except auto_recipes.RecipeError:
                automatic = None
            result[installed.appid] = {**cached[1], "preferred": catalog.preferred_build(self.gpu, automatic)}
        return result

    def _find(self, appid: str) -> games.Installed | None:
        hint = (self.state["games"].get(appid) or {}).get("shortcut_hint")
        return games.find_installed(self.home, appid) or games.from_hint(appid, hint, self.home)

    def _identity(self, installed: games.Installed, entry: dict) -> dict | None:
        """Real game behind a non-Steam shortcut; worked out once, then remembered."""
        if not installed.shortcut or installed.native:
            return None
        cached = entry.get("identity")
        if isinstance(cached, dict):
            return cached
        exe = installed.root / installed.exe if installed.exe else None
        entry["identity"] = identify.identify(installed.name, installed.root, exe, search=self.search)
        self._save()
        return entry["identity"]

    def _recipe(self, appid: str, identity: dict | None, installed: games.Installed | None = None):
        steam_appid = str(identity.get("steam_appid") or appid) if identity else str(appid)
        live = None
        if installed is not None:
            found = self.wiki.lookup(identity.get("name") if identity else None, installed.name)
            if found:
                live = recipes.from_facts(steam_appid, found, "optiscaler-wiki@live", self.wiki.page_facts(found.get("page")))
        recipe = recipes.recipe_for(steam_appid, live, game_build=installed.build_id if installed else None)
        return recipes.with_engine(recipe, appid, installed.root) if installed else recipe

    def refresh_wiki(self, appid: str | None = None) -> dict:
        result = self.wiki.refresh()
        if appid:
            installed = self._find(str(appid))
            recipe = self._recipe(str(appid), self._identity(installed, self._game_state(str(appid))), installed) if installed else None
            page = self.wiki.refresh_page(recipe.page if recipe else None)
            result = {"updated": result["updated"] or page["updated"], "fresh": result["fresh"] and page["fresh"]}
        return result

    def search_games(self, term: str) -> list[dict]:
        return self.search(identify.clean_name(term) or term)[:8]

    def set_identity(self, appid: str, steam_appid: int | None, name: str | None) -> dict:
        entry = self._game_state(appid)
        if steam_appid:
            entry["identity"] = identify.from_override(int(steam_appid), str(name or steam_appid))
        else:
            entry.pop("identity", None)
        self._save()
        return self.game(appid)

    def game(self, appid: str, hint: dict | None = None) -> dict:
        if isinstance(hint, dict) and hint.get("exe"):
            entry = self._game_state(appid)
            clean = {k: str(hint.get(k) or "")[:1024] for k in ("exe", "dir", "name", "opts")}
            if entry.get("shortcut_hint") != clean:
                entry["shortcut_hint"] = clean
                self._save()
        installed = self._find(appid)
        if installed is None:
            raise UpscalerError("not_installed")
        entry = self._game_state(appid)
        identity = self._identity(installed, entry)
        recipe = self._recipe(appid, identity, installed)
        analysis = NATIVE_ANALYSIS if installed.native else games.analyze(
            installed.root, entry.get("exe"), recipe.exe if recipe else installed.exe)
        install = entry.get("install")
        automatic = None
        recipe_info = _recipe_info(recipe)
        if recipe_info and (installed.native or not analysis.get("inputs", {}).get(recipe_info["recommended_input"])):
            recipe_info["recommended_input"] = None
        if recipe_info and "luma" in recipe_info["needs"]:
            recipe_info["luma_detected"] = luma.detected(installed.root, Path(analysis["target"]) if analysis["target"] else None, recipe.appid)
        if recipe_info:
            try:
                automatic = auto_recipes.plan(recipe, installed)
                recipe_info["automatic"] = ["Luma"] if automatic and any(d.startswith("luma") for d in automatic.dependencies) else []
                recipe_info["automatic_builds"] = [b.id for b in catalog.BUILDS.values() if b.engine == "optiscaler"] if automatic else []
                recipe_info["user_files"] = auto_recipes.user_files(automatic, self.user_files)
                recipe_info["blocked"] = auto_recipes.unresolved(recipe, analysis, automatic)
            except auto_recipes.RecipeError:
                recipe_info["automatic"] = []
                recipe_info["blocked"] = True
        solutions = {}
        for candidate in catalog.BUILDS.values():
            solutions[candidate.id] = _build_solution(self.gpu, analysis, recipe, candidate, automatic,
                                                      bool(recipe_info and recipe_info.get("blocked")))
        selected = solutions.get((install or {}).get("build")) or solution_plan.resolve(self.gpu, analysis, recipe)
        return {
            "solution": selected, "solutions": solutions,
            "preferred": catalog.preferred_build(self.gpu, automatic),
            "appid": appid,
            "name": installed.name,
            "updating": games.update_state(installed.state_flags),
            "shortcut": installed.shortcut,
            "native": installed.native,
            "launcher": installed.launcher[0] if installed.launcher else None,
            "identity": identity,
            "analysis": analysis,
            "install": {**install, "status": self._status(install, entry),
                        "quality_check": _quality_check(install, _facts(install))} if isinstance(install, dict) else None,
            "history": entry.get("history", [])[-HISTORY_LIMIT:],
            "recipe": recipes.applies(recipe),
            "recipe_info": recipe_info,
            "foreign_backup": {"at": entry["foreign_backup"]["at"]} if isinstance(entry.get("foreign_backup"), dict) else None,
            "fg_note": recipe.fg_note if recipe else None,
            "fg_plan": None if installed.native else selected["fg_plan"],
        }

    # ---- files only the user can download ---------------------------------
    def _user_dependency(self, dependency_id: str):
        dependency = recipe_catalog.bundled().dependencies.get(str(dependency_id))
        if dependency is None or dependency.kind != "user_files":
            raise UpscalerError("unknown_dependency")
        return dependency

    def user_file_candidates(self, dependency_id: str) -> dict:
        home = Path(self.home)
        folders = [home / "Downloads", home / "Descargas"]
        folder = next((f for f in folders if f.is_dir()), home)
        return {"folder": str(folder), "candidates": user_deps.candidates(self._user_dependency(dependency_id), folders)}

    def add_user_file(self, appid: str, dependency_id: str, path: str) -> dict:
        dependency = self._user_dependency(dependency_id)
        chosen = Path(str(path))
        allowed = (Path(self.home).resolve(), Path("/run/media"))
        try:
            resolved = chosen.resolve(strict=True)
        except OSError:
            raise UpscalerError("user_file_unreadable") from None
        if not any(resolved.is_relative_to(root) for root in allowed):
            raise UpscalerError("user_file_unreadable")
        try:
            self.user_files.adopt(dependency, resolved)
        except user_deps.UserFileError as error:
            raise UpscalerError("user_file_wrong" if error.code in ("missing_files", "ambiguous_files")
                                else "user_file_unreadable") from None
        return self.game(appid)

    def remove_user_file(self, appid: str, dependency_id: str) -> dict:
        self.user_files.remove(self._user_dependency(dependency_id))
        return self.game(appid)

    def set_exe(self, appid: str, exe: str | None) -> dict:
        installed = self._find(appid)
        if installed is None:
            raise UpscalerError("not_installed")
        entry = self._game_state(appid)
        if exe is None:
            entry.pop("exe", None)
        else:
            path = Path(exe)
            resolved = (path if path.is_absolute() else installed.root / path).resolve()
            if not resolved.is_file() or not resolved.is_relative_to(installed.root.resolve()) or resolved.suffix.lower() != ".exe":
                raise UpscalerError("invalid_exe")
            entry["exe"] = resolved.relative_to(installed.root.resolve()).as_posix()
        self._save()
        return self.game(appid)

    # ---- jobs ----------------------------------------------------------------
    def job(self) -> dict | None:
        with self._lock:
            return dict(self._job) if self._job else None

    def _update_job(self, **fields) -> None:
        with self._lock:
            if self._job is not None:
                self._job.update(fields)

    def begin(self, kind: str, appid: str) -> str:
        with self._image_lock:
            return self._begin(kind, appid)

    def _begin(self, kind: str, appid: str) -> str:
        with self._lock:
            if self._job and self._job.get("state") == "running":
                raise UpscalerError("busy")
            self._cancel.clear()
            self._job = {
                "id": uuid.uuid4().hex[:12], "kind": kind, "appid": appid, "state": "running",
                "phase": "prepare", "done": 0, "total": 0, "error": None, "started": time.time(),
            }
            return self._job["id"]

    def cancel(self) -> dict | None:
        self._cancel.set()
        return self.job()

    def run(self, operation, *args) -> None:
        appid = str(args[0]) if args else ""
        requested = args[1] if len(args) > 1 and isinstance(args[1], dict) else None
        self._fallbacks = {}
        self.record_action(appid, operation.__name__, "started", requested)
        try:
            result = operation(*args)
            self._update_job(state="done", phase="done", result=result)
        except (UpscalerError, AssetError) as error:
            detail = getattr(error, "detail", "")
            if detail and self.logger:
                self.logger.warning(f"Upscaler job failed: {error.code} ({detail})")
            self._update_job(state="error", error=error.code, detail=detail or None)
        except Exception as error:  # noqa: BLE001
            if self.logger:
                self.logger.warning(f"Upscaler job failed: {type(error).__name__}")
            self._update_job(state="error", error="internal_error")
        finally:
            job = self.job() or {}
            self.record_action(appid, operation.__name__, job.get("state", "unknown"), requested, job.get("error"))

    def begin_scaler_transition(self, appid: str) -> dict:
        with self._image_lock:
            installed = self._find(appid)
            if installed is None:
                raise UpscalerError("not_installed")
            if games.running_under(installed.root, self.proc):
                raise UpscalerError("running")
            if self.job() and self.job().get("state") == "running":
                raise UpscalerError("busy")
            try:
                pending = self.scaler_transitions.pending(appid)
            except scaler_transition.TransitionError as error:
                raise UpscalerError(str(error)) from None
            if pending:
                if Path(pending["root"]) != installed.root.resolve():
                    raise UpscalerError("transition_conflict")
                return {"token": pending["token"], "restore": pending["restore"],
                        "previous_mako": pending.get("previous_mako"), "recovery": True}
            if installed.launcher:
                raise UpscalerError("transition_unsupported")
            if games.update_state(installed.state_flags):
                raise UpscalerError("updating")
            entry = self._game_state(appid)
            install = entry.get("install")
            if install and install.get("engine", "optiscaler") not in ("optiscaler", "dll"):
                raise UpscalerError("transition_unsupported")
            if not install and not installed.native and self.game(appid)["analysis"]["foreign"]:
                raise UpscalerError("foreign")
            restore = {"overrides": _overrides(install) if install.get("engine") != "dll" else [],
                       "args": list(install.get("args", [])), "env": {}} if install else None
            try:
                return self.scaler_transitions.begin(appid, installed.root, entry, restore,
                                                     install.get("target") if install else None,
                                                     self.mako_status(appid).get("profiles", {}).get(appid),
                                                     self._managed_configuration(install.get("target")) if install else {})
            except scaler_transition.TransitionError as error:
                raise UpscalerError(str(error)) from None
            except (OSError, ValueError):
                raise UpscalerError("transition_conflict") from None

    def finish_scaler_transition(self, appid: str, token: str, rollback: bool = False) -> dict | None:
        with self._image_lock:
            installed = self._find(appid)
            if installed is None:
                raise UpscalerError("not_installed")
            if games.running_under(installed.root, self.proc):
                raise UpscalerError("running")
            if self.job() and self.job().get("state") == "running":
                raise UpscalerError("busy")
            try:
                pending = self.scaler_transitions.pending(appid)
                if not pending or pending.get("token") != token or Path(pending["root"]) != installed.root.resolve():
                    raise scaler_transition.TransitionError("transition_token")
                if rollback and "rollback_result" not in pending:
                    current = self._game_state(appid).get("install") or {}
                    prior = pending.get("restore")
                    removed = {"removed_overrides": list(current.get("added_overrides", [])),
                               "removed_args": list(current.get("added_args", [])), "env": _owned_env(current)}
                    pending["rollback_result"] = ({"overrides": [], "args": [], **removed, **(prior or {}),
                                                   "env": {**removed["env"], **(prior or {}).get("env", {})}}
                                                  if prior or any(removed.values()) else None)
                    self.scaler_transitions._save(pending)
                receipt = pending.get("recipe_prefix")
                if pending.get("recipe_dependencies"):
                    receipt = prefix_dependencies.recover_pending(self.home, installed) or receipt
                if rollback and receipt:
                    prefix_dependencies.rollback(receipt, installed.root, self.proc)
                try:
                    checkpoint = self.scaler_transitions.finish(appid, token, rollback)
                except scaler_transition.TransitionError as error:
                    if not rollback or str(error) != "transition_conflict":
                        raise
                    # The game replaced files Panel had installed (an update or verify): those are the game's now,
                    # so the change is kept as it is instead of leaving the game stuck between two states.
                    if self.logger:
                        self.logger.warning("Upscaler rollback found game-updated files; keeping the current install")
                    if receipt:
                        prefix_dependencies.finish(receipt, self.proc)
                    self.scaler_transitions.clear(appid)
                    return None
                if rollback:
                    if receipt:
                        checkpoint["recipe_prefix"] = receipt
                        self.scaler_transitions._save(checkpoint)
                    self.state["games"][appid] = copy.deepcopy(checkpoint["entry"])
                    self._save()
                    return checkpoint.get("rollback_result")
                if receipt:
                    prefix_dependencies.finish(receipt, self.proc)

                self.scaler_transitions.clear(appid)
                return None
            except scaler_transition.TransitionError as error:
                raise UpscalerError(str(error)) from None
            except prefix_dependencies.DependencyError as error:
                raise UpscalerError(error.code) from None
            except (OSError, ValueError):
                raise UpscalerError("transition_conflict") from None

    # ---- install -------------------------------------------------------------
    def _guard(self, appid: str, confirm_anti_cheat: bool = False) -> tuple[games.Installed, dict, Path]:
        installed = self._find(appid)
        if installed is None:
            raise UpscalerError("not_installed")
        if installed.native:
            raise UpscalerError("native_game")
        update = games.update_state(installed.state_flags)
        if update:
            raise UpscalerError("updating" if update == "running" else "update_pending")
        if games.running_under(installed.root, self.proc):
            raise UpscalerError("running")
        recipe = self._recipe(appid, self._identity(installed, self._game_state(appid)), installed)
        analysis = games.analyze(installed.root, self._game_state(appid).get("exe"), recipe.exe if recipe else installed.exe)
        if not analysis["target"]:
            raise UpscalerError("no_exe")
        if analysis["anti_cheat"] and not confirm_anti_cheat:
            raise UpscalerError("anti_cheat")
        return installed, analysis, Path(analysis["target"])

    def install(self, appid: str, choice: dict) -> dict:
        build = catalog.BUILDS.get(str(choice.get("build")))
        if build is None or not build.available:
            raise UpscalerError("unknown_build")
        if self.scaler_transitions.pending(appid) and build.engine not in ("optiscaler", "dll"):
            raise UpscalerError("transition_unsupported")
        if build.engine == "dll":
            return self._install_dll(appid, build, choice)
        if build.engine == "helixsr":
            return self._install_helix(appid, build, choice)
        if build.engine == "proton":
            return self._install_proton(appid, build, choice)
        if choice.get("proxy") and str(choice["proxy"]) not in catalog.PROXIES:
            raise UpscalerError("invalid_proxy")

        installed, analysis, target = self._guard(appid, bool(choice.get("confirm_anti_cheat")))
        entry = self._game_state(appid)
        recipe = self._recipe(appid, self._identity(installed, entry), installed)
        try:
            automatic = auto_recipes.plan(recipe, installed)
            if auto_recipes.unresolved(recipe, analysis, automatic):
                raise UpscalerError("recipe_unresolved")
        except auto_recipes.RecipeError as error:
            raise UpscalerError(error.code) from None
        if automatic and diagnostics._steam_config(self.home, appid).get("launch_diagnostics", {}).get("reshade_redirected"):
            raise UpscalerError("recipe_unsupported")
        if automatic and not self.scaler_transitions.pending(appid):
            raise UpscalerError("recipe_transaction_required")
        effective_build = catalog.for_game(build, analysis["inputs"], self.gpu, recipe)
        solution = solution_plan.resolve(self.gpu, analysis, recipe, catalog.ASSETS[effective_build.archive].generation,
                                         build.engine, choice.get("fg_route"), dependencies_ready=bool(automatic))
        _requested_fg(solution, choice)
        previous = entry.get("install") if isinstance(entry.get("install"), dict) else {}
        edited = previous.get("edited", {}) if previous.get("engine", "optiscaler") == "optiscaler" else {}
        image_overrides = previous.get("image_overrides", {}) if previous.get("engine", "optiscaler") == "optiscaler" else {}
        if image_overrides:
            old_text = image_settings.read(Path(previous["target"]) / "OptiScaler.ini", installed.root)
            image_overrides = _image_overrides(previous, old_text)
        def needed(chosen_build, chosen_recipe) -> list[catalog.Asset]:
            result = catalog.build_assets(chosen_build)
            if chosen_recipe:
                result += [catalog.ASSETS[a] for a in dict.fromkeys(chosen_recipe.files.values()) if catalog.ASSETS[a] not in result]
                if chosen_recipe.optipatcher:
                    result.append(catalog.ASSETS[catalog.OPTIPATCHER])
            return result + auto_recipes.assets(automatic)

        # Everything is downloaded before the current install comes out: a failed or cancelled download leaves
        # the game exactly as it was.
        self._recover_orphan(target)
        pinned_only: set[str] = set()
        paths, chosen = self._fetch_assets(needed(effective_build, recipe))
        try:
            auto_recipes.sources(automatic, paths, self.user_files)
        except auto_recipes.RecipeError:
            pinned_only = {asset.id for asset in auto_recipes.assets(automatic)}
            paths, chosen = self._fetch_assets(needed(effective_build, recipe), pinned_only)
        left = self._replace(entry, installed)
        # Files the game replaced since (an update) stayed behind with stale backups: those copies go, the game's stay.
        self._recover_orphan(target)
        if left is not None:
            analysis = games.analyze(installed.root, entry.get("exe"), analysis["exe"])
        if analysis["foreign"]:
            raise UpscalerError("foreign")

        recipe = self._recipe(appid, entry.get("identity"), installed)
        proxy = str(choice.get("proxy") or _recipe_proxy(recipe) or "dxgi.dll")
        build = catalog.for_game(build, analysis["inputs"], self.gpu, recipe)
        assets = needed(build, recipe)
        if any(asset.id not in paths for asset in assets):
            paths, chosen = self._fetch_assets(assets, pinned_only)

        self._update_job(phase="copy")
        archive_asset = catalog.ASSETS[build.archive]
        archive = paths[build.archive]
        sources = _archive_sources(archive, archive_asset.generation)
        base_ini = sources.pop("OptiScaler.ini").read_text(encoding="utf-8", errors="replace")
        injector = sources.pop("OptiScaler.dll")
        if build.injector:
            injector = paths[build.injector]
        sources[proxy] = injector
        prefix = f"{build.extra_dir}/" if build.extra_dir else ""
        for name, asset_id in build.replace.items():
            sources[prefix + name] = paths[asset_id]
        for asset_id in build.assets:
            sources[prefix + catalog.ASSETS[asset_id].filename] = paths[asset_id]
        if recipe:
            for name, asset_id in recipe.files.items():
                sources[name] = paths[asset_id]
            if recipe.optipatcher:
                sources[f"{prefix}plugins/OptiPatcher.asi"] = paths[catalog.OPTIPATCHER]

        try:
            sources = {**auto_recipes.sources(automatic, paths, self.user_files), **sources}
        except auto_recipes.RecipeError as error:
            raise UpscalerError(error.code) from None
        solution = solution_plan.resolve(self.gpu, analysis, recipe, archive_asset.generation, build.engine, choice.get("fg_route"), dependencies_ready=bool(automatic))
        fg_plan = _requested_fg(solution, choice)
        wiki_ini = wiki.resolve_settings(base_ini, recipe.wiki_settings) if recipe else {}
        panel = {
            **catalog.BASE_INI, **build.ini, **(recipe.ini if recipe else {}), **_option_overrides(choice),
            **({"Plugins.LoadAsiPlugins": "true"} if recipe and recipe.optipatcher else {}),
            **catalog.model_overrides(build, choice.get("model")),
            **catalog.fg_overrides(fg_plan, choice.get("fg") == "on"),
        }
        managed = sorted(panel)
        # The wiki's settings are a starting point the user may change in the editor; Panel's own keys win over them
        # and hand edits from the advanced editor survive a repair or a new version.
        overrides = {**{k: v for k, v in wiki_ini.items() if k not in panel}, **panel}
        overrides.update({k: v for k, v in edited.items() if k not in panel})
        image_overrides = {k: v for k, v in image_overrides.items() if k in image_settings.MANAGED_SHARPNESS_KEYS and ini.read(base_ini, k) is not None}
        if image_overrides:
            before_image = ini.apply(base_ini, overrides)
            entry["image_settings"] = {"target": str(target / "OptiScaler.ini"),
                                       "original": {k: ini.read(before_image, k) for k in image_overrides},
                                       "applied": dict(image_overrides)}
            overrides.update(image_overrides)
        else:
            entry.pop("image_settings", None)
        if automatic:
            self._update_job(phase="dependencies")
            try:
                checkpoint = self.scaler_transitions.pending(appid)
                checkpoint["recipe_dependencies"] = True
                self.scaler_transitions._save(checkpoint)
                receipt = prefix_dependencies.prepare(self.home, installed, auto_recipes.verbs(automatic), self.logger, self.proc)
                if receipt:
                    checkpoint["recipe_prefix"] = receipt
                    self.scaler_transitions._save(checkpoint)
                    prefix_dependencies.publish(receipt, installed.root, self.proc)
            except prefix_dependencies.DependencyError as error:
                raise UpscalerError(error.code) from None
        self._update_job(phase="copy")
        with tempfile.TemporaryDirectory(prefix="recipe-", dir=self.cache.root) as prepared:
            try:
                sources.update(auto_recipes.configured_sources(automatic, target, Path(prepared)))
            except auto_recipes.RecipeError as error:
                raise UpscalerError(error.code) from None
            existing = target / REFRAMEWORK_CONFIG
            reframework = recipe and ("reframework-nightly" in recipe.files.values()
                                      or any(n.lower() == "dinput8.dll" for n in recipes._dependency_files(recipe)))
            if reframework and not existing.is_symlink():
                try:
                    current = existing.read_text(encoding="utf-8", errors="replace") if existing.is_file() and existing.stat().st_size < 1024 * 1024 else ""
                except OSError:
                    current = ""
                seed = Path(prepared) / REFRAMEWORK_CONFIG
                seed.write_text(_with_keys(current, REFRAMEWORK_CLOSED), encoding="utf-8")
                sources[REFRAMEWORK_CONFIG] = seed
            manifest = self._apply(target, sources, ini.apply(base_ini, overrides),
                                   getattr(automatic, "configuration", {}) if automatic else {})

        now = time.time()
        entry["install"] = {
            "build": build.id, "archive": build.archive, "proxy": proxy, "target": str(target), "exe": analysis["exe"],
            "installed_at": now, "options": _clean_options(choice), "solution": solution,
            "native_dlls": list(recipe.native_dlls) if recipe else [],
            "game_build": installed.build_id,
            "recipe_revision": automatic.revision if automatic else None,
            "recipe_configuration": dict(getattr(automatic, "configuration", {})) if automatic else {},
            "recipe_dependencies": list(automatic.dependencies) if automatic else [],
            "components": diagnostics.components([self._component(chosen[asset.id]) for asset in assets]),
            "fg_plan": fg_plan,
            "managed": managed,
            "edited": dict(edited),
            "image_overrides": dict(image_overrides),
            "menu_key": recipe.menu_key if recipe else None,
            "args": list(recipe.args) if recipe else [],
            "added_args": [],
        }
        _wrote_ini(entry["install"])
        entry["history"].append({
            "build": build.id, "proxy": proxy, "at": now, "result": "pending", "exe": analysis["exe"],
            "game_build": installed.build_id, "recipe_revision": automatic.revision if automatic else None,
        })
        entry["history"] = entry["history"][-HISTORY_LIMIT:]
        if installed.launcher:
            try:
                self._launcher_overrides(installed, entry["install"], remove=False)
            except UpscalerError:
                self._remove(target)
                entry["install"] = None
                self._save()
                raise
            self._save()
            return _with_leftovers({"files": len(manifest["files"]), "overrides": [], "args": [],
                                    "launcher": installed.launcher[0]}, left)
        self._save()
        return _with_leftovers({"files": len(manifest["files"]), "overrides": _overrides(entry["install"]),
                                "args": entry["install"]["args"]}, left)

    def _fetch_assets(self, assets: list[catalog.Asset], pinned_only=frozenset()) -> tuple[dict[str, Path], dict[str, catalog.Asset]]:
        """Each asset at its newest verified release, falling back to the catalog's own when that one fails."""
        unique = list({asset.id: asset for asset in assets}.values())
        self._fallbacks.update({asset.id: "layout" for asset in unique
                                if asset.id in pinned_only and self.latest.tracked(asset)})
        if any(self.latest.tracked(asset) and asset.id not in pinned_only for asset in unique):
            self._update_job(phase="resolve", total=0, done=0)
        chosen = {asset.id: asset if asset.id in pinned_only else self.latest.resolve(asset) for asset in unique}
        missing = [asset for asset in chosen.values() if not self.cache.ready(asset)]
        total = sum(asset.size for asset in missing)
        if missing:
            self._update_job(phase="download", total=total, done=0)
        paths: dict[str, Path] = {}
        offset = 0
        for pinned in unique:
            asset = chosen[pinned.id]
            base = offset
            progress = (lambda received, base=base: self._update_job(done=base + received)) if asset in missing else (lambda _done: None)
            try:
                paths[pinned.id] = self.cache.ensure(asset, progress, self._cancel.is_set)
            except AssetError as error:
                if asset == pinned or error.code in ("cancelled", "no_space"):
                    raise
                if self.logger:
                    self.logger.warning(f"Newest {pinned.id} failed ({error.code}); using the catalog's release")
                self._fallbacks[pinned.id] = error.code
                chosen[pinned.id] = pinned
                paths[pinned.id] = self.cache.ensure(pinned, progress, self._cancel.is_set)
            if asset in missing:
                offset += asset.size
                self._update_job(done=offset)
        return paths, chosen

    def _component(self, asset: catalog.Asset) -> dict:
        """Which release went in for a tracked tool: the newest (with its tag) or the catalog's, and why."""
        item = {"id": asset.id, "sha256": asset.sha256}
        if self.latest.tracked(asset):
            version = self.latest.version(asset)
            item.update({"source": "latest", "version": version} if version else
                        {"source": "pinned", "fallback": self._fallbacks.get(asset.id, "unresolved")})
        return item

    def _install_dll(self, appid: str, build: catalog.Build, choice: dict) -> dict:
        installed, analysis, _target = self._guard(appid, bool(choice.get("confirm_anti_cheat")))
        name = "amd_fidelityfx_upscaler_dx12.dll"
        loader = "amd_fidelityfx_loader_dx12.dll"
        framegen = "amd_fidelityfx_framegeneration_dx12.dll"
        legacy = "amd_fidelityfx_dx12.dll"
        if name not in build.replace or set(build.replace) - {name, loader, framegen}:
            raise UpscalerError("dll_unsupported")
        targets = analysis.get("dll_targets", [])
        has_legacy = any(Path(path).name.lower() == legacy for path in targets)
        if set(build.legacy_replace) - {loader, framegen}:
            raise UpscalerError("dll_unsupported")
        entry = self._game_state(appid)
        replacements = dict(build.replace)
        if has_legacy or isinstance(entry.get("install"), dict):
            replacements.update(build.legacy_replace)
        assets = {}
        for destination, asset_id in replacements.items():
            asset = catalog.ASSETS.get(asset_id)
            if asset is None or Path(asset.member or asset.filename).name.lower() != destination or asset.archive:
                raise UpscalerError("dll_unsupported")
            assets[destination] = asset
        if not targets:
            raise UpscalerError("dll_no_target")
        if any(Path(path).name.lower() == legacy for path in targets) and not {loader, framegen} <= assets.keys():
            raise UpscalerError("dll_unsupported")
        provider_dirs = {Path(path).parent for path in targets if Path(path).name.lower() in {name, legacy}}
        if loader not in build.replace and any(Path(path).name.lower() == loader and Path(path).parent not in provider_dirs for path in targets):
            raise UpscalerError("dll_unsupported")
        root = installed.root
        for relative in targets:
            path = root / relative
            siblings = {p.name.lower(): p for p in path.parent.iterdir()}
            checked = [path, siblings.get(name, path.parent / name)]
            if path.name.lower() == legacy:
                checked.append(siblings.get(framegen, path.parent / framegen))
            if any(p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) for p in checked):
                raise UpscalerError("unsafe_folder")
        if analysis["foreign"] and not isinstance(entry.get("install"), dict):
            raise UpscalerError("foreign")
        fetched, _chosen = self._fetch_assets(list(assets.values()))
        downloaded = {destination: fetched[asset.id] for destination, asset in assets.items()}
        left = self._replace(entry, installed)
        root = installed.root
        self._recover_orphan(root)
        if (root / games.MANIFEST_DIR).exists():
            raise UpscalerError("dll_conflict")
        if left is not None:
            analysis = games.analyze(root, entry.get("exe"), analysis["exe"])
            targets = analysis.get("dll_targets", [])
        if not targets:
            raise UpscalerError("dll_no_target")
        provider_dirs = {Path(path).parent for path in targets if Path(path).name.lower() in {name, legacy}}
        if loader not in build.replace and any(Path(path).name.lower() == loader and Path(path).parent not in provider_dirs for path in targets):
            raise UpscalerError("dll_unsupported")
        targets = [path for path in targets if Path(path).name.lower() != loader or loader in build.replace]
        sources = {}
        for relative in targets:
            path = root / relative
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
                raise UpscalerError("dll_no_target")
            lower = path.name.lower()
            if lower == legacy:
                if not {loader, framegen} <= downloaded.keys():
                    raise UpscalerError("dll_unsupported")
                sources[relative] = downloaded[loader]
            elif lower in downloaded:
                sources[relative] = downloaded[lower]
            else:
                raise UpscalerError("dll_unsupported")
            siblings = {p.name.lower(): p for p in path.parent.iterdir()}
            provider = siblings.get(name, path.parent / name)
            sources[provider.relative_to(root).as_posix()] = downloaded[name]
            if lower == legacy and framegen not in siblings:
                sources[(path.parent / framegen).relative_to(root).as_posix()] = downloaded[framegen]
        for relative in sources:
            path = root / relative
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise UpscalerError("unsafe_folder")
        self._update_job(phase="copy")
        self._apply(root, sources, None)
        now = time.time()
        entry["install"] = {
            "build": build.id, "engine": "dll", "way": "fsr", "proxy": None,
            "target": str(root), "exe": analysis["exe"], "dll_targets": targets,
            "installed_at": now, "options": _clean_options({"fg": "off"}),
            "native_dlls": [], "fg_plan": None, "args": [], "added_args": [],
        }
        entry["history"].append({"build": build.id, "proxy": None, "at": now, "result": "not_run", "exe": analysis["exe"]})
        entry["history"] = entry["history"][-HISTORY_LIMIT:]
        self._save()
        return _with_leftovers({"files": len(sources), "overrides": [], "args": []}, left)

    def _install_helix(self, appid: str, build: catalog.Build, choice: dict) -> dict:
        installed, analysis, target = self._guard(appid, bool(choice.get("confirm_anti_cheat")))
        if build.way == "fsr" and "fsr31" not in analysis["inputs"]:
            raise UpscalerError("helixsr_no_fsr")
        entry = self._game_state(appid)
        pinned = catalog.ASSETS[build.archive]
        newest = self.latest.resolve(pinned) if self.helix.ready() else None
        if not self.helix.ready() or (newest and (self.helix.digest() or pinned.sha256) != newest.sha256):
            paths, chosen = self._fetch_assets([pinned])
            self._update_job(phase="unpack")
            try:
                self._helix("unpack", paths[pinned.id], chosen[pinned.id].sha256)
            except UpscalerError:
                if chosen[pinned.id] == pinned:
                    raise
                paths, chosen = self._fetch_assets([pinned], {pinned.id})
                self._helix("unpack", paths[pinned.id], pinned.sha256)
            shutil.rmtree(paths[pinned.id].parent, ignore_errors=True)
        left = self._replace(entry, installed)
        if left is not None:
            analysis = games.analyze(installed.root, entry.get("exe"), analysis["exe"])
        if analysis["foreign"]:
            raise UpscalerError("foreign")

        self._update_job(phase="copy")
        game = self._helix("install", installed.root)
        exe_folder = Path(game.get("exe_folder") or target)
        options = _clean_options({**choice, "fg": "off"})
        log = Path(game["log_path"]) if game.get("log_path") else exe_folder / "helixsr.log"
        meta = target / games.MANIFEST_DIR
        meta.mkdir(exist_ok=True)
        atomic_json_save(str(meta / HELIX_MARKER), {"way": build.way, "release": self.helix.release.name})
        ownership.own_like(target, [meta])

        now = time.time()
        entry["install"] = {
            "build": build.id, "engine": "helixsr", "way": build.way,
            "proxy": None,
            "target": str(target), "exe": analysis["exe"], "exe_folder": str(exe_folder), "log": str(log),
            "helix_file": str(log.parent / HELIX_INSTALL_FILE),
            "installed_at": now, "options": options, "native_dlls": [], "fg_plan": None,
            "args": [], "added_args": [],
        }
        entry["history"].append({"build": build.id, "proxy": entry["install"]["proxy"], "at": now,
                                 "result": "pending", "exe": analysis["exe"]})
        entry["history"] = entry["history"][-HISTORY_LIMIT:]
        if installed.launcher and _overrides(entry["install"]):
            try:
                self._launcher_overrides(installed, entry["install"], remove=False)
            except UpscalerError:
                self._drop(entry["install"], installed.root)
                entry["install"] = None
                self._save()
                raise
            self._save()
            return _with_leftovers({"files": 0, "overrides": [], "args": [], "launcher": installed.launcher[0]}, left)
        self._save()
        return _with_leftovers({"files": 0, "overrides": _overrides(entry["install"]), "args": []}, left)

    def _install_proton(self, appid: str, build: catalog.Build, choice: dict) -> dict:
        """Proton swaps the game's FSR 3.1 for FSR 4 at launch: nothing is written into the game."""
        env = str(choice.get("env") or "")
        if env not in PROTON_FSR4_ENVS:
            raise UpscalerError("proton_env")
        installed, analysis, target = self._guard(appid, bool(choice.get("confirm_anti_cheat")))
        if "fsr31" not in analysis["inputs"]:
            raise UpscalerError("proton_no_fsr")
        entry = self._game_state(appid)
        left = self._replace(entry, installed)
        now = time.time()
        entry["install"] = {
            "build": build.id, "engine": "proton", "env": env, "proxy": None, "target": str(target),
            "exe": analysis["exe"], "installed_at": now, "options": _clean_options({**choice, "fg": "off"}),
            "native_dlls": [], "fg_plan": None, "args": [], "added_args": [],
        }
        entry["history"].append({"build": build.id, "proxy": None, "at": now, "result": "pending", "exe": analysis["exe"]})
        entry["history"] = entry["history"][-HISTORY_LIMIT:]
        self._save()
        return _with_leftovers({"files": 0, "overrides": [], "args": [], "env": {env: "1"}}, left)

    def _replace(self, entry: dict, installed: games.Installed) -> dict | None:
        """Take the game's current install out; what it left in the launch options comes back to undo."""
        old = entry.get("install")
        if not isinstance(old, dict):
            return None
        entry["previous"] = diagnostics.snapshot(old)
        self._drop(old, installed.root)
        if old.get("launcher"):
            try:
                self._launcher_overrides(installed, old, remove=True)
            except UpscalerError:
                pass
        entry["install"] = None
        self._save()
        left = {"overrides": [] if old.get("launcher") else _owned_overrides(old),
                "args": list(old.get("added_args", [])), "env": _owned_env(old)}
        # If the new install fails after this point, the error still tells the page what to take out.
        self._update_job(leftover={"removed_overrides": left["overrides"], "removed_args": left["args"], "env": left["env"]})
        return left

    def _recover_orphan(self, target: Path) -> None:
        """Clear what no install claims: an interrupted install, or a removal that kept files the game replaced."""
        meta = target / games.MANIFEST_DIR
        if meta.is_symlink() or not meta.is_dir() or (meta / HELIX_MARKER).exists():
            return
        for entry in self.state.get("games", {}).values():
            install = entry.get("install")
            if isinstance(install, dict) and Path(str(install.get("target", ""))) == target:
                return
        if (meta / "manifest.json").is_file():
            self._remove(target)
        else:
            backup = meta / "backup"
            if backup.is_dir() and not backup.is_symlink():
                for saved in sorted(backup.rglob("*"), reverse=True):
                    if saved.is_file() and not saved.is_symlink():
                        destination = target / saved.relative_to(backup)
                        if not destination.is_symlink() and destination.resolve().is_relative_to(target.resolve()):
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            os.replace(saved, destination)
        if self.logger:
            self.logger.info("Upscaler leftovers from an interrupted or kept install were cleared")
        shutil.rmtree(meta, ignore_errors=True)

    def _helix(self, method: str, *args):
        try:
            return getattr(self.helix, method)(*args)
        except helixsr.HelixError as error:
            raise UpscalerError(error.code, error.detail) from None

    def _drop(self, install: dict, root: Path) -> list[str]:
        """Take an install out of the game, whichever engine put it there."""
        if install.get("engine") == "proton":
            return []
        if not _is_helix(install):
            return self._remove(Path(install["target"]))
        if self.helix.ready():
            self._helix("remove", root)
        else:
            helixsr.remove_by_hand(Path(install.get("helix_file", "")).parent)
        log = Path(install.get("log", ""))
        for generated in (log, log.with_name(helixsr.HLX_FSR_LOG)):
            if generated.name and generated.is_file():
                generated.unlink()
        shutil.rmtree(Path(install["target"]) / games.MANIFEST_DIR, ignore_errors=True)
        return []

    def _apply(self, target: Path, sources: dict[str, Path], ini_text: str | None, configuration=None) -> dict:
        names = [*sources, *(["OptiScaler.ini", *_GENERATED] if ini_text is not None else [])]
        try:
            with self.scaler_transitions.mutation(target, names):
                return self._apply_files(target, sources, ini_text, configuration)
        except scaler_transition.TransitionError as error:
            raise UpscalerError(str(error)) from None

    def _apply_files(self, target: Path, sources: dict[str, Path], ini_text: str | None, configuration=None) -> dict:
        meta = target / games.MANIFEST_DIR
        if meta.is_symlink():
            raise UpscalerError("unsafe_folder")
        backup = meta / "backup"
        meta.mkdir(exist_ok=True)
        manifest: dict = {"files": {}, "backups": [], "dirs": [], "configuration": configuration or {}, "incomplete": True}
        if ini_text is None:
            manifest["engine"] = "dll"
        journal = str(meta / "manifest.json")
        # Every move is journaled before it happens, so a service killed mid-copy leaves a manifest that restores
        # the game's originals instead of mistaking Panel's own files for them on the next attempt.
        try:
            for relative, source in sources.items():
                manifest["files"][relative] = None
                self._place(target, relative, manifest, backup, journal)
                shutil.copyfile(source, target / relative)
                manifest["files"][relative] = sha256(target / relative)
            if ini_text is not None:
                manifest["files"]["OptiScaler.ini"] = None
                self._place(target, "OptiScaler.ini", manifest, backup, journal)
                (target / "OptiScaler.ini").write_text(ini_text, encoding="utf-8")
            for generated in _GENERATED if ini_text is not None else ():
                if (target / generated).exists():
                    self._place(target, generated, manifest, backup, journal)
        except BaseException:
            atomic_json_save(journal, manifest)
            self._remove_files(target, configuration)
            raise
        manifest.pop("incomplete")
        atomic_json_save(journal, manifest)
        ownership.own_like(target, [*(target / f for f in manifest["files"]), *(target / d for d in manifest["dirs"]), meta])
        return manifest

    @staticmethod
    def _place(target: Path, relative: str, manifest: dict, backup: Path, journal: str | None = None) -> None:
        destination = target / relative
        for parent in reversed(Path(relative).parents[:-1]):
            if not (target / parent).exists():
                manifest["dirs"].append(parent.as_posix())
                if journal:
                    atomic_json_save(journal, manifest)
                (target / parent).mkdir()
        if destination.exists() or destination.is_symlink():
            saved = backup / relative
            if relative not in manifest["backups"]:
                manifest["backups"].append(relative)
            if journal:
                atomic_json_save(journal, manifest)
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists() or saved.is_symlink():
                # The oldest copy is the game's original; whatever sits in the game now came later.
                destination.unlink()
            else:
                os.replace(destination, saved)
        elif journal:
            atomic_json_save(journal, manifest)

    # ---- options, uninstall, verify -----------------------------------------
    def configure(self, appid: str, choice: dict) -> dict:
        with self._image_lock:
            return self._configure(appid, choice)

    def _configure(self, appid: str, choice: dict) -> dict:
        entry = self._game_state(appid)
        install = entry.get("install")
        if not isinstance(install, dict):
            raise UpscalerError("not_patched")
        if install.get("engine") == "dll":
            raise UpscalerError("dll_no_options")
        installed = self._find(appid)
        current = install.get("options") or {}
        unchanged = {**current, "build": install.get("build"), "proxy": install.get("proxy")}
        only_disable = (install.get("engine", "optiscaler") == "optiscaler"
                        and current.get("fg") == "on" and choice.get("fg") == "off"
                        and all(key == "fg" or key in unchanged and value == unchanged[key]
                                for key, value in choice.items()))
        if only_disable:
            if installed and games.running_under(installed.root, self.proc):
                raise UpscalerError("running")
            path = Path(install["target"]) / "OptiScaler.ini"
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                path.write_text(ini.apply(text, catalog.fg_overrides(None, False)), encoding="utf-8")
            except OSError:
                raise UpscalerError("broken") from None
            _wrote_ini(install)
            install["options"] = {**current, "fg": "off"}
            self._save()
            return {"options": install["options"]}
        solution = None
        if installed and not installed.native and install.get("engine", "optiscaler") == "optiscaler":
            recipe = self._recipe(appid, self._identity(installed, entry), installed)
            analysis = games.analyze(installed.root, entry.get("exe"), recipe.exe if recipe else installed.exe)
            try:
                automatic = auto_recipes.plan(recipe, installed)
                if auto_recipes.unresolved(recipe, analysis, automatic):
                    raise UpscalerError("recipe_unresolved")
            except auto_recipes.RecipeError as error:
                raise UpscalerError(error.code) from None
            solution = solution_plan.resolve(self.gpu, analysis, recipe, _generation(install), route=choice.get("fg_route"),
                                             dependencies_ready=bool(automatic))
        if solution:
            _requested_fg(solution, choice)
        if installed and games.running_under(installed.root, self.proc):
            result = self._configure_running(install, choice)
            if solution:
                install["solution"] = solution
                self._save()
            return result
        if _is_helix(install) or install.get("engine") == "proton":
            install["options"] = _clean_options({**choice, "fg": "off"})
            self._save()
            return {"options": install["options"]}
        path = Path(install["target"]) / "OptiScaler.ini"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raise UpscalerError("broken") from None
        plan = _requested_fg(solution, choice) if solution else install.get("fg_plan")
        install["fg_plan"] = catalog.fg_route_plan(plan, choice.get("fg_route"))
        if solution:
            install["solution"] = solution
        fg = catalog.fg_overrides(install.get("fg_plan"), choice.get("fg") == "on")
        build = catalog.BUILDS.get(install.get("build", ""))
        model = catalog.model_overrides(build, choice.get("model"))
        model_changed = model != catalog.model_overrides(build, install.get("options", {}).get("model"))
        path.write_text(ini.apply(text, {**_option_overrides(choice, reset=True), **model, **fg, **_image_overrides(install, text)}), encoding="utf-8")
        _wrote_ini(install)
        if _clean_options(choice).get("quality") != (install.get("options") or {}).get("quality"):
            install["quality_at"] = time.time()
        install["options"] = _clean_options(choice)
        if model_changed:
            now = time.time()
            install["verification_since"] = now
            entry["history"].append({"build": install["build"], "proxy": install.get("proxy"),
                                     "model": install["options"]["model"], "at": now, "result": "pending"})
            entry["history"] = entry["history"][-HISTORY_LIMIT:]
        self._save()
        return {"options": install["options"]}

    def _configure_running(self, install: dict, choice: dict) -> dict:
        """Quality and sharpness while the game runs: OptiScaler reads its INI only at start, so the change is saved
        for the next launch (the panel offers to restart the game); anything else waits for the game to close."""
        current = _clean_options(install.get("options") or {})
        wanted = _clean_options({**current, **choice})
        if _is_helix(install) or install.get("engine") == "proton" or any(
                wanted.get(k) != current.get(k) for k in ("fg", "fg_route", "model")):
            raise UpscalerError("running")
        path = Path(install["target"]) / "OptiScaler.ini"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raise UpscalerError("broken") from None
        path.write_text(ini.apply(text, {**_option_overrides(choice, reset=True), **_image_overrides(install, text)}), encoding="utf-8")
        _wrote_ini(install)
        if wanted.get("quality") != current.get("quality"):
            install["quality_at"] = time.time()
        install["options"] = wanted
        self._save()
        return {"options": install["options"], "live": False}

    # ---- another tool's install --------------------------------------------------------------
    def adopt_foreign(self, appid: str) -> dict:
        """Set another tool's OptiScaler or HelixSR aside (kept, restorable) so Panel's can go in cleanly."""
        installed, _analysis, target = self._guard(appid, True)
        entry = self._game_state(appid)
        if isinstance(entry.get("install"), dict):
            raise UpscalerError("still_patched")
        if games.foreign_identity(target)["engine"] == "helixsr":
            raise UpscalerError("foreign_helix")
        items, swaps = games.foreign_items(target), games.helix_swaps(target)
        if not items and not swaps:
            raise UpscalerError("no_foreign")
        backup = self.state_path.parent / "foreign" / str(appid) / str(int(time.time()))
        backup.mkdir(parents=True, exist_ok=True)
        # Recorded before anything moves and after every item, so an interrupted move stays restorable.
        record = {"dir": str(backup), "target": str(target), "items": [], "swaps": [], "at": time.time()}
        entry["foreign_backup"] = record
        self._save()
        for name in items:
            shutil.move(str(target / name), str(backup / name))
            record["items"].append(name)
            self._save()
        for name in swaps:
            original = target / Path(name).with_suffix(".original.dll").name
            if (target / name).exists():
                shutil.move(str(target / name), str(backup / name))
            os.replace(original, target / name)
            record["swaps"].append(name)
            self._save()
        return {"moved": [*record["items"], *record["swaps"]]}

    def restore_foreign(self, appid: str) -> dict:
        entry = self._game_state(appid)
        record = entry.get("foreign_backup")
        if not isinstance(record, dict):
            raise UpscalerError("no_foreign")
        if isinstance(entry.get("install"), dict):
            raise UpscalerError("still_patched")
        installed = self._find(appid)
        if installed and games.running_under(installed.root, self.proc):
            raise UpscalerError("running")
        target, backup = Path(record["target"]), Path(record["dir"])
        restored, skipped = [], []
        for name in list(record.get("swaps", [])):
            if (target / name).exists():
                os.replace(target / name, target / Path(name).with_suffix(".original.dll").name)
            if (backup / name).exists():
                shutil.move(str(backup / name), str(target / name))
            restored.append(name)
            record["swaps"].remove(name)
        for name in list(record.get("items", [])):
            if (target / name).exists():
                skipped.append(name)
                continue
            if (backup / name).exists():
                shutil.move(str(backup / name), str(target / name))
            restored.append(name)
            record["items"].remove(name)
        ownership.own_like(target, [target / name for name in restored])
        if skipped:
            # Something new sits where the old file was: the copy stays until that is sorted out.
            self._save()
            return {"restored": restored, "kept": skipped}
        shutil.rmtree(backup, ignore_errors=True)
        entry.pop("foreign_backup", None)
        self._save()
        return {"restored": restored}

    def _image_target(self, appid: str, writing: bool = False):
        installed = self._find(appid)
        if installed is None:
            raise UpscalerError("not_installed")
        if installed.native:
            raise UpscalerError("not_supported")
        if writing:
            if (self.job() or {}).get("state") == "running":
                raise UpscalerError("busy")
            update = games.update_state(installed.state_flags)
            if update:
                raise UpscalerError("updating" if update == "running" else "update_pending")
        entry = self._game_state(appid)
        install = entry.get("install")
        owned = isinstance(install, dict) and install.get("engine", "optiscaler") == "optiscaler"
        # OptiScaler reads its INI only at start and never writes it while running, so Panel's own install can take
        # a new value for the next launch; another tool's files wait for the game to close.
        if writing and not owned and games.running_under(installed.root, self.proc):
            raise UpscalerError("running")
        if isinstance(install, dict) and not owned:
            raise UpscalerError("not_supported")
        if owned:
            target = Path(install["target"])
        else:
            analysis = games.analyze(installed.root, entry.get("exe"), installed.exe)
            if not analysis.get("target"):
                raise UpscalerError("unsupported_layout")
            target = Path(analysis["target"])
        text = image_settings.read(target / "OptiScaler.ini", installed.root)
        helix = False
        if not owned:
            identity = games.foreign_identity(target)
            if identity["engine"] != "helixsr" or identity["variant"] != "dlss" or identity["manifest_error"]:
                raise UpscalerError("unsupported_layout")
            if "HelixSR Scaler" not in text or "HelixSR.Int8" not in image_settings.values(text):
                raise UpscalerError("unsupported_layout")
            providers = ("HelixSR/helixsr.dll", "HelixSR-fsrfg/amd_fidelityfx_dx12.dll")
            if not any((target / name).is_file() and not (target / name).is_symlink()
                       and not (target / name).parent.is_symlink() for name in providers):
                raise UpscalerError("unsupported_layout")
            helix = True
        return installed.root, target / "OptiScaler.ini", text, helix, owned

    def image_settings(self, appid: str) -> dict:
        with self._image_lock:
            try:
                _, path, text, helix, _ = self._image_target(appid)
                receipt = self._game_state(appid).get("image_settings", {})
                return image_settings.state(text, helix, receipt.get("target") == str(path) and bool(receipt.get("applied")))
            except (UpscalerError, image_settings.SettingsError) as error:
                reason = error.code if isinstance(error, UpscalerError) else str(error)
                return {"supported": False, "sharpness": None, "int8": None, "managed": False, "reason": reason}

    def set_image_settings(self, appid: str, values: dict) -> dict:
        with self._image_lock:
            try:
                root, path, text, helix, owned = self._image_target(appid, True)
                changes = image_settings.changes(values, image_settings.state(text, helix, False), text)
                entry = self._game_state(appid)
                previous = entry.get("image_settings")
                receipt = json.loads(json.dumps(previous)) if isinstance(previous, dict) and previous.get("target") == str(path) else {
                    "target": str(path), "original": {}, "applied": {}}
                current = image_settings.values(text)
                for key, value in changes.items():
                    if key not in receipt["original"] or current.get(key) != receipt["applied"].get(key):
                        receipt["original"][key] = current[key]
                    receipt["applied"][key] = value
                previous_overrides = entry["install"].get("image_overrides") if owned else None
                entry["image_settings"] = receipt
                if owned:
                    entry["install"]["image_overrides"] = dict(receipt["applied"])
                try:
                    self._save()
                    image_settings.write(path, root, text, ini.apply(text, changes))
                    if owned:
                        _wrote_ini(entry["install"])
                except Exception:
                    if image_settings.read(path, root) == text:
                        if previous is None:
                            entry.pop("image_settings", None)
                        else:
                            entry["image_settings"] = previous
                        if owned:
                            if previous_overrides is None:
                                entry["install"].pop("image_overrides", None)
                            else:
                                entry["install"]["image_overrides"] = previous_overrides
                        self._save()
                    raise
                return self.image_settings(appid)
            except image_settings.SettingsError as error:
                raise UpscalerError(str(error)) from None

    def restore_image_settings(self, appid: str) -> dict:
        with self._image_lock:
            try:
                root, path, text, _, owned = self._image_target(appid, True)
                entry = self._game_state(appid)
                receipt = entry.get("image_settings")
                if not isinstance(receipt, dict) or receipt.get("target") != str(path):
                    raise UpscalerError("image_settings_changed")
                image_settings.write(path, root, text, image_settings.restored(text, receipt))
                if owned:
                    _wrote_ini(entry["install"])
                previous_overrides = entry["install"].get("image_overrides") if owned else None
                entry.pop("image_settings", None)
                if owned:
                    entry["install"].pop("image_overrides", None)
                try:
                    self._save()
                except Exception:
                    entry["image_settings"] = receipt
                    if owned and previous_overrides is not None:
                        entry["install"]["image_overrides"] = previous_overrides
                    raise
                return self.image_settings(appid)
            except image_settings.SettingsError as error:
                raise UpscalerError(str(error)) from None

    # ---- advanced: every OptiScaler.ini key ---------------------------------------------------
    def _ini_path(self, appid: str) -> tuple[dict, Path]:
        install = self._game_state(appid).get("install")
        if not isinstance(install, dict) or install.get("engine") in ("proton", "helixsr", "dll"):
            raise UpscalerError("not_patched")
        return install, Path(install["target"]) / "OptiScaler.ini"

    def ini_schema(self, appid: str) -> dict:
        install, path = self._ini_path(appid)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raise UpscalerError("broken") from None
        return {"sections": ini.schema(text, _managed_keys(install))}

    def set_ini(self, appid: str, dotted: str, value: str) -> dict:
        with self._image_lock:
            return self._set_ini(appid, dotted, value)

    def _set_ini(self, appid: str, dotted: str, value: str) -> dict:
        """One key the user changed by hand; Panel's own keys stay Panel's so it never overwrites a choice silently."""
        install, path = self._ini_path(appid)
        value = str(value).strip()
        if not value or len(value) > 200 or any(c in value for c in "\r\n[]"):
            raise UpscalerError("ini_value")
        text = path.read_text(encoding="utf-8", errors="replace")
        if "." not in str(dotted):
            # A bare `Key` as the OptiScaler wiki writes it; only taken when the installed INI has exactly one.
            dotted = next(iter(wiki.resolve_settings(text, {str(dotted): value})), str(dotted))
        section, _, key = str(dotted).partition(".")
        entry = next((k for s in ini.schema(text) if s["name"] == section for k in s["keys"] if k["key"] == key), None)
        if entry is None:
            raise UpscalerError("ini_key")
        if dotted in _managed_keys(install):
            raise UpscalerError("ini_managed")
        if entry["choices"] and value not in entry["choices"]:
            raise UpscalerError("ini_value")
        path.write_text(ini.apply(text, {dotted: value}), encoding="utf-8")
        install.setdefault("edited", {})[dotted] = value
        _wrote_ini(install)
        self._save()
        return {"key": dotted, "value": value}

    def uninstall(self, appid: str) -> dict:
        entry = self._game_state(appid)
        install = entry.get("install")
        if not isinstance(install, dict):
            raise UpscalerError("not_patched")
        installed = self._find(appid)
        if installed and games.running_under(installed.root, self.proc):
            raise UpscalerError("running")
        self._update_job(phase="restore")
        if _is_helix(install) and installed is None:
            raise UpscalerError("not_installed")
        entry["previous"] = diagnostics.snapshot(install)
        kept = self._drop(install, installed.root if installed else Path(install["target"]))
        if install.get("launcher") and installed:
            try:
                self._launcher_overrides(installed, install, remove=True)
            except UpscalerError:
                # The launcher's config moved or went away: nothing left there to undo.
                pass
            result = {"kept": kept, "overrides": [], "args": [], "launcher": install["launcher"][0]}
        else:
            result = {"kept": kept, "overrides": _owned_overrides(install), "args": install.get("added_args", [])}
        if install.get("engine") == "proton":
            result["env"] = _owned_env(install)
        entry["install"] = None
        self._save()
        return result

    def _launcher_overrides(self, installed: games.Installed, install: dict, remove: bool) -> None:
        """Heroic/Lutris keep their own per-game environment; Steam's launch options never reach Wine."""
        game = launchers.find(self.home, *installed.launcher) if installed.launcher else None
        if game is None:
            raise UpscalerError("launcher_missing")
        dlls = [o.split("=", 1)[0] for o in _overrides(install)]
        try:
            launchers.set_overrides(game, dlls, remove=remove)
        except OSError:
            raise UpscalerError("launcher_write") from None
        install["launcher"] = list(installed.launcher)

    def record_added_args(self, appid: str, args: list[str], overrides: list[str] | None = None,
                          env: list[str] | None = None) -> dict:
        """Remember what Panel itself added to the launch options, so removal never strips the user's own."""
        install = self._game_state(appid).get("install")
        if not isinstance(install, dict):
            raise UpscalerError("not_patched")
        install["added_args"] = [a for a in args if a in install.get("args", [])]
        if overrides is not None:
            install["added_overrides"] = [o for o in overrides if o in _overrides(install)]
        if env is not None:
            install["added_env"] = [k for k in env if k == install.get("env")]
        self._save()
        return {"added_args": install["added_args"]}

    def _managed_configuration(self, target) -> dict:
        for appid, entry in self.state.get("games", {}).items():
            install = entry.get("install")
            if install and install.get("target") == str(target):
                identity = entry.get("identity") or {}
                return auto_recipes.installed_configuration(install, identity.get("steam_appid") or appid)
        return {}

    def _remove(self, target: Path) -> list[str]:
        try:
            manifest = json.loads((target / games.MANIFEST_DIR / "manifest.json").read_text())
        except (OSError, ValueError):
            manifest = {}
        names = [*manifest.get("files", {}), *manifest.get("backups", []),
                 *(_GENERATED if manifest.get("engine") != "dll" else ())]
        try:
            with self.scaler_transitions.mutation(target, names):
                return self._remove_files(target, self._managed_configuration(target))
        except auto_recipes.RecipeError as error:
            raise UpscalerError(error.code) from None
        except (OSError, UnicodeError):
            raise UpscalerError("recipe_files_invalid") from None
        except scaler_transition.TransitionError as error:
            raise UpscalerError(str(error)) from None

    @staticmethod
    def _remove_files(target: Path, configuration=None) -> list[str]:
        meta = target / games.MANIFEST_DIR
        try:
            manifest = json.loads((meta / "manifest.json").read_text())
        except (OSError, ValueError):
            return []
        configuration = manifest.get("configuration", configuration or {})
        kept = []
        backups = set(manifest.get("backups", []))
        for relative, digest in manifest.get("files", {}).items():
            path = target / relative
            if not path.is_file():
                continue
            if digest is None and relative in backups and not (meta / "backup" / relative).exists():
                continue
            if digest is None or sha256(path) == digest or (relative in _SEEDED and relative not in backups):
                path.unlink()
            elif relative in configuration:
                auto_recipes.restore_configuration(path, meta / "backup" / relative, configuration[relative])
            elif relative in _SEEDED:
                # REFramework rewrote its config while installed: only the keys Panel set go back to the user's.
                saved = meta / "backup" / relative
                original = saved.read_text(encoding="utf-8", errors="replace") if saved.is_file() else ""
                current = path.read_text(encoding="utf-8", errors="replace")
                path.write_text(_with_keys(current, _keys(original, REFRAMEWORK_CLOSED)), encoding="utf-8")
                saved.unlink(missing_ok=True)
            else:
                kept.append(relative)
        for generated in _GENERATED if manifest.get("engine") != "dll" else ():
            if (target / generated).is_file() and generated not in manifest.get("backups", []):
                (target / generated).unlink()
        for relative in manifest.get("backups", []):
            saved = meta / "backup" / relative
            if saved.exists() and not (target / relative).exists():
                os.replace(saved, target / relative)
        for directory in sorted(manifest.get("dirs", []), key=len, reverse=True):
            try:
                (target / directory).rmdir()
            except OSError:
                pass
        if not kept:
            shutil.rmtree(meta, ignore_errors=True)
        return kept

    def capture_frame(self, appid: str) -> dict:
        """Grab the running game's frame for the comparison and label it with what is installed."""
        install = self._game_state(appid).get("install")
        if not isinstance(install, dict):
            raise UpscalerError("not_patched")
        installed = self._find(appid)
        if installed is None or not games.running_under(installed.root, self.proc):
            raise UpscalerError("not_running")
        name = f"{appid}-{int(time.time() * 1000)}"
        try:
            path = capture.take(self.state_path.parent / "compare", name)
        except capture.CaptureError as error:
            raise UpscalerError(error.code) from None
        facts = _facts(install)
        return {
            "id": name,
            "build": install.get("build"),
            "resolution": facts.get("resolution"),
            "upscaler": facts.get("upscaler"),
            "image": capture.data_url(path),
        }

    def live(self, appid: str) -> dict:
        """Read-only look at the log while the game runs; never touches history."""
        install = self._game_state(appid).get("install")
        if not isinstance(install, dict):
            return {"result": "not_patched"}
        if install.get("engine") == "dll":
            return {"result": self._status(install, self._game_state(appid)), "resolution": None, "fg": None, "fg_toggle": False}
        facts = _facts(install)
        blind = bool(facts.get("fg_blind"))
        generating: bool | None = None
        if not blind and "fg_state" in facts:
            generating = facts["fg_state"] == "true" and bool(facts.get("fg"))
        elif not blind and facts.get("fg"):
            generating = True
        return {"result": _verdict(install, facts), "resolution": facts.get("resolution"),
                "resolution_source": facts.get("resolution_source", "unavailable"), "fg": generating, "fg_toggle": not blind,
                **logread.provider_observation(facts if install.get("engine", "optiscaler") == "optiscaler" else {})}

    # ---- lsfg-vk -----------------------------------------------------------------------------
    def _ensure_engine_idle(self):
        if self.engine_game_running():
            raise engine_updates.UpdateError("engine_deferred")
        roots = [installed.root for appid in self.state.get("games", {}) if (installed := self._find(appid))]
        try:
            entries = list(Path(self.proc).iterdir())
            uid = Path(self.home).stat().st_uid
            seen = False
            for process in entries:
                if not process.name.isdecimal():
                    continue
                try:
                    if process.stat().st_uid != uid:
                        continue
                    seen = True
                    env = (process / "environ").read_bytes()[:131072].split(b"\0")
                    cmd = (process / "cmdline").read_bytes()[:16384].decode("utf-8", "replace").lower()
                    for value in env:
                        key, _, content = value.partition(b"=")
                        if key in (b"SteamAppId", b"SteamGameId") and content.isdigit() and int(content):
                            raise engine_updates.UpdateError("engine_deferred")
                    if ".exe" in cmd or any(str(root).lower() in cmd for root in roots):
                        raise engine_updates.UpdateError("engine_deferred")
                except FileNotFoundError:
                    continue
            if not seen:
                raise engine_updates.UpdateError("engine_deferred")
        except OSError as error:
            raise engine_updates.UpdateError("engine_deferred") from error

    def refresh_engine(self, engine: str, apply: bool = False) -> dict:
        if engine not in ("mako", "lsfg") or type(apply) is not bool:
            raise UpscalerError("engine_unknown")
        with self._engine_lock:
            status = self.mako.status() if engine == "mako" else self.lsfg.status()
            current = status.get("version") or (mako.VERSION if engine == "mako" else catalog.LSFG_ARCHIVE.removeprefix("lsfg-vk-"))
            current = current.removeprefix("lsfg-vk-")
            result = {"state": "current", "version": current}
            if engine == "lsfg" and status.get("foreign") or engine == "mako" and not status.get("supported"):
                return {**result, "state": "unmanaged"}
            try:
                cached = self._engine_checks.get(engine)
                if cached is None or cached[0] + 60 < time.monotonic() or cached[1] != current:
                    candidate = engine_updates.discover(engine, current)
                    self._engine_checks[engine] = (time.monotonic(), current, candidate)
                    self.record_action("global", "engine_check_" + engine, "done", {"build": current, "value": candidate["version"] if candidate else current})
                    if self.logger:
                        self.logger.info("Upscaler engine=%s current=%s available=%s", engine, current, candidate["version"] if candidate else "none")
                else:
                    candidate = cached[2]
                if not candidate:
                    return result
                result.update(state="available", available=candidate["version"])
                if not apply or not status.get("installed"):
                    return result
                self._ensure_engine_idle()
                self.record_action("global", "engine_update_" + engine, "started", {"build": candidate["version"]})
                asset = engine_updates.prepare(engine, candidate, self.cache)
                if engine == "mako":
                    self.mako.install(self.cache, asset=asset, version=candidate["version"], before_commit=self._ensure_engine_idle)
                else:
                    with tempfile.TemporaryDirectory(prefix="lsfg-update-", dir=self.cache.root) as temp:
                        unpacked = Path(temp)
                        engine_updates.unpack_lsfg(self.cache.file(asset), unpacked, lsfg.LAYER_FILES)
                        self.lsfg.install(unpacked, "lsfg-vk-" + candidate["version"], before_commit=self._ensure_engine_idle)
                self._engine_checks.pop(engine, None)
                self.record_action("global", "engine_update_" + engine, "done", {"build": candidate["version"]})
                return {"state": "updated", "version": candidate["version"]}
            except Exception as error:
                code = getattr(error, "code", "engine_check_failed")
                state = "deferred" if code == "engine_deferred" else "failed"
                self.record_action("global", "engine_update_" + engine, state, {"build": current}, code)
                return {**result, "state": state}

    def lsfg_status(self) -> dict:
        return self.lsfg.status()

    def lsfg_install(self) -> dict:
        if self.lsfg.status()["installed"]:
            return self.lsfg.status()
        asset = catalog.ASSETS[catalog.LSFG_ARCHIVE]
        try:
            unpacked = self.cache.ensure(asset, lambda _done: None, lambda: False)
            return self.lsfg.install(unpacked, asset.id)
        except AssetError as error:
            raise UpscalerError(error.code) from None
        except lsfg.LsfgError as error:
            raise UpscalerError(error.code) from None

    def lsfg_adopt_foreign(self) -> dict:
        try:
            self.lsfg.adopt_foreign()
        except lsfg.LsfgError as error:
            raise UpscalerError(error.code) from None
        return self.lsfg_install()

    def lsfg_restore_foreign(self) -> dict:
        try:
            cleared = self.lsfg.uninstall().get("cleared", [])
            return {**self.lsfg.restore_foreign(), "cleared": cleared}
        except lsfg.LsfgError as error:
            raise UpscalerError(error.code) from None

    def lsfg_uninstall(self) -> dict:
        return self.lsfg.uninstall()

    def lsfg_game(self, appid: str, config: dict | None) -> dict:
        installed = self._find(appid)
        if installed is None:
            raise UpscalerError("not_installed")
        exe = installed.exe
        if config is not None and not installed.native:
            entry = self._game_state(appid)
            recipe = self._recipe(appid, self._identity(installed, entry), installed)
            exe = games.analyze(installed.root, entry.get("exe"), recipe.exe if recipe else installed.exe)["exe"]
        try:
            return self.lsfg.set_game(appid, installed.name, config, exe)
        except lsfg.LsfgError as error:
            raise UpscalerError(error.code) from None

    @staticmethod
    def _shortcut_launch_identity(installed: games.Installed) -> str:
        root = installed.root.resolve()
        exe = str((root / installed.exe).resolve()) if installed.exe else None
        identity = json.dumps([str(root), exe, installed.launcher], separators=(",", ":"))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _launch_owner(self, appid: str, *, mako_profile: bool = False, claim: bool = True) -> str:
        installed = self._find(appid)
        if installed is None or not installed.shortcut:
            return appid
        digest = self._shortcut_launch_identity(installed)
        for previous, entry in self.state["games"].items():
            if previous == appid or entry.get("launch_identity") != digest:
                continue
            other = self._find(previous)
            if other is not None and other.shortcut and self._shortcut_launch_identity(other) == digest:
                raise UpscalerError("mako_identity_ambiguous")
        if claim:
            entry = self._game_state(appid)
            if entry.get("launch_identity") != digest:
                entry["launch_identity"] = digest
                self._save()
        return str(int(digest[:16], 16)) if mako_profile else "ns:" + digest

    def mako_status(self, appid: str | None = None) -> dict:
        status = self.mako.status()
        if appid is None:
            return status
        try:
            pending_transition = self.scaler_transitions.pending(appid) is not None
        except scaler_transition.TransitionError:
            pending_transition = True
        status = {**status, "scaler_transition_pending": pending_transition}
        try:
            key = self._launch_owner(appid, mako_profile=True, claim=False)
        except UpscalerError as error:
            if error.code != "mako_identity_ambiguous":
                raise
            return {**status, "ready": False, "reason": error.code, "profiles": {}}
        profiles = dict(status.get("profiles", {}))
        if key != appid and key in profiles:
            profiles[appid] = profiles.pop(key)
        return {**status, "profiles": profiles}

    def mako_install(self) -> dict:
        if self.mako.status()["installed"]:
            return self.mako.status()
        try:
            return self.mako.install(self.cache)
        except (AssetError, mako.MakoError) as error:
            raise UpscalerError(error.code) from None

    def mako_game(self, appid: str, config: dict | None) -> dict:
        installed = self._find(appid)
        if installed is None:
            raise UpscalerError("not_installed")
        exe = installed.exe
        if config is not None and not installed.native:
            entry = self._game_state(appid)
            recipe = self._recipe(appid, self._identity(installed, entry), installed)
            exe = games.analyze(installed.root, entry.get("exe"), recipe.exe if recipe else installed.exe)["exe"]
        try:
            return self.mako.set_game(self._launch_owner(appid, mako_profile=True), installed.name, config, exe)
        except mako.MakoError as error:
            raise UpscalerError(error.code) from None

    def mako_runtime(self, appid: str) -> dict:
        try:
            return self.mako.runtime(self._launch_owner(appid, mako_profile=True, claim=False))
        except mako.MakoError as error:
            raise UpscalerError(error.code) from None

    def get_launch_receipt(self, appid: str, owner: str) -> dict | None:
        try:
            return self.launch_receipts.get(self._launch_owner(appid, claim=False), owner)
        except ValueError as error:
            raise UpscalerError(str(error)) from None

    def set_launch_receipt(self, appid: str, owner: str, receipt: dict | None) -> bool:
        try:
            return self.launch_receipts.set(self._launch_owner(appid), owner, receipt)
        except ValueError as error:
            raise UpscalerError(str(error)) from None

    def press_key(self, appid: str, action: str) -> dict:
        """OptiScaler hotkeys for devices without a keyboard; only while the game runs."""
        install = self._game_state(appid).get("install")
        if not isinstance(install, dict):
            raise UpscalerError("not_patched")
        if install.get("engine") == "dll":
            raise UpscalerError("dll_no_options")
        installed = self._find(appid)
        if installed is None or not games.running_under(installed.root, self.proc):
            raise UpscalerError("not_running")
        try:
            self.press(install.get("menu_key") or action if action == "menu" else action)
        except keys.HotkeyError as error:
            raise UpscalerError(str(error)) from None
        return {"pressed": action}

    def verify(self, appid: str) -> dict:
        entry = self._game_state(appid)
        install = entry.get("install")
        if not isinstance(install, dict):
            raise UpscalerError("not_patched")
        facts = _facts(install)
        result = _verdict(install, facts)
        if self._status(install, entry) == "broken":
            result = "broken"
        history = entry.get("history") or []
        if history and history[-1].get("build") == install.get("build") and result != "not_run":
            history[-1]["result"] = result
            history[-1]["facts"] = {k: facts[k] for k in ("upscaler", "input", "fg", "resolution", "initial_resolution", "resolution_source", "version") if k in facts}
            self._save()
        return {"result": result, "facts": facts}

    def diagnose(self, appid: str) -> dict:
        appid = str(appid)
        entry = self.state["games"].get(appid, {})
        installed = self._find(appid)
        report = diagnostics.game_report(self.home, appid, entry, installed)
        report["image_settings"] = self.image_settings(appid)
        report["solution"] = diagnostics.solution((entry.get("install") or {}).get("solution"))
        try:
            profile_key = self._launch_owner(appid, mako_profile=True, claim=False)
            if profile_key in self.mako.status().get("profiles", {}):
                report["mako_profile"] = profile_key
        except UpscalerError as error:
            report["mako_reason"] = error.code
        recipe = self._recipe(appid, entry.get("identity"), installed)
        report["current_solution"] = None
        if installed:
            analysis = NATIVE_ANALYSIS if installed.native else games.analyze(
                installed.root, entry.get("exe"), recipe.exe if recipe else installed.exe)
            automatic = None
            try:
                automatic = auto_recipes.plan(recipe, installed)
                blocked = auto_recipes.unresolved(recipe, analysis, automatic)
            except auto_recipes.RecipeError:
                blocked = True
            build = catalog.BUILDS.get((entry.get("install") or {}).get("build"))
            current = (_build_solution(self.gpu, analysis, recipe, build, automatic, blocked) if build else
                       solution_plan.resolve(self.gpu, analysis, recipe))
            report["current_solution"] = diagnostics.solution(current)
            owned = []
            # OptiScaler keeps its manifest beside the executable, the DLL route in the game root.
            for folder in dict.fromkeys(f for f in (analysis.get("target"), str(installed.root)) if f):
                try:
                    owned += list(json.loads((Path(folder) / games.MANIFEST_DIR / "manifest.json").read_text()).get("files", {}))
                except (OSError, ValueError, TypeError, AttributeError):
                    continue
            if not installed.native:
                report["game_files"] = diagnostics.game_files(installed, analysis, owned)
                report["proton_prefix"] = diagnostics.proton_prefix(self.home, appid)
        info = _recipe_info(recipe)
        report["recipe"] = diagnostics.fields(info, ("status", "broken", "linux", "optipatcher", "proxy"))
        if info:
            report["recipe"]["needs"] = [str(item)[:80] for item in info.get("needs", [])[:16]]
            report["recipe"]["inputs"] = [str(item)[:40] for item in info.get("inputs", [])[:16]]
            report["recipe"].update(
                appid=recipe.appid, revision=recipe.catalog_revision, catalog_version=recipe.catalog_version,
                file=f"game-recipes/games/{recipe.appid}.json" if recipe.dependencies else None,
                dependencies=list(recipe.dependencies), required_args=list(recipe.args),
            )
            if installed:
                try:
                    automatic = auto_recipes.plan(recipe, installed)
                    analysis = games.analyze(installed.root, entry.get("exe"), recipe.exe or installed.exe)
                    report["recipe"]["blocked"] = auto_recipes.unresolved(recipe, analysis, automatic)
                    if automatic:
                        report["recipe"]["prefix"] = prefix_dependencies.status(self.home, installed, auto_recipes.verbs(automatic))
                    if "luma" in recipe.needs:
                        report["recipe"]["luma_detected"] = luma.detected(installed.root, Path(analysis["target"]) if analysis["target"] else None, recipe.appid)
                except (auto_recipes.RecipeError, prefix_dependencies.DependencyError) as error:
                    report["recipe"].update(blocked=True, error=error.code)
        return report

    def report(self, context=None) -> dict:
        context = diagnostics.frontend_context(context)
        touched = [(appid, entry) for appid, entry in self.state["games"].items()
                   if isinstance(entry.get("install"), dict) or entry.get("history") or entry.get("exe")
                   or entry.get("actions") or entry.get("identity")]
        touched.sort(key=lambda item: max([h.get("at", 0) for h in
                     [*item[1].get("history", []), *item[1].get("actions", [])]] or [0]), reverse=True)
        job = self.job()
        priority = [str(value) for value in ((context.get("running") or {}).get("live_appid"),
                    (job or {}).get("appid")) if value is not None]
        appids = list(dict.fromkeys([*priority, *(appid for appid, _ in touched)]))[:12]
        reports = []
        for appid in appids:
            try:
                reports.append(self.diagnose(appid))
            except Exception as error:
                reports.append({"appid": appid, "error": type(error).__name__})
        return {
            "gpu": self.gpu, "device": self.device, "frontend": context,
            # What the user was offered on this GPU, so a "not supported" complaint shows what Panel showed.
            "builds": [diagnostics.fields(row, ("id", "supported", "may_fallback"))
                       for row in catalog.describe(self.gpu, self.device) if row.get("available")],
            "global_actions": diagnostics.report_actions(self.state.get("global_actions")),
            "environment": diagnostics.environment(),
            "cached_assets": [a.id for a in catalog.ASSETS.values() if self.cache.ready(a)],
            "job": diagnostics.with_job_reference(diagnostics.fields(job, ("id", "appid", "kind", "state", "phase", "done", "total", "error", "started")), "id"),
            "lsfg": self.lsfg.report(),
            "mako": self.mako.report(),
            "helixsr": {"downloaded": self.helix.ready(), "release": self.helix.release.name},
            "games": reports,
        }

    def support_state(self) -> dict:
        mako_status = self.mako.status()
        return {
            "gpu": self.gpu,
            "mako": {key: mako_status[key] for key in ("installed", "ready", "reason", "profiles") if key in mako_status},
            "installs": {
                appid: {
                    "build": entry["install"].get("build"),
                    "engine": entry["install"].get("engine", "optiscaler"),
                    "dll_targets": entry["install"].get("dll_targets", []),
                    "proxy": entry["install"].get("proxy"),
                    "exe": entry["install"].get("exe"),
                    "options": entry["install"].get("options"),
                    "last": (entry.get("history") or [{}])[-1].get("result"),
                }
                for appid, entry in self.state["games"].items()
                if isinstance(entry.get("install"), dict)
            },
        }


_ALWAYS_MANAGED = {
    *catalog.BASE_INI,
    "QualityOverrides.QualityRatioOverrideEnabled", "Sharpness.OverrideSharpness", "Sharpness.Sharpness",
    "FrameGen.Enabled", "FrameGen.FGInput", "FrameGen.FGOutput", "OptiFG.HUDFix",
    *(f"QualityOverrides.QualityRatio{m}" for m in ("DLAA", "UltraQuality", "Quality", "Balanced", "Performance", "UltraPerformance")),
}


def _managed_keys(install: dict) -> set[str]:
    build = catalog.BUILDS.get(str(install.get("build")))
    model_keys = {k for _, keys in (build.models if build else ()) for k in keys}
    return {*_ALWAYS_MANAGED, *install.get("managed", []), *(build.ini if build else {}), *model_keys}


def _owned_overrides(install: dict) -> list[str]:
    """Overrides Panel added; installs from before this was recorded own all of theirs."""
    return list(install["added_overrides"]) if "added_overrides" in install else _overrides(install)


def _owned_env(install: dict) -> dict:
    if install.get("engine") != "proton":
        return {}
    if "added_env" in install and install["env"] not in install["added_env"]:
        return {}
    return {install["env"]: None}


def _with_leftovers(result: dict, left: dict | None) -> dict:
    """Launch-option entries the replaced install added and the new one does not reuse."""
    if not left:
        return result
    result["removed_overrides"] = [o for o in left["overrides"] if o not in result.get("overrides", [])]
    result["removed_args"] = [a for a in left["args"] if a not in result.get("args", [])]
    stale = {k: v for k, v in left["env"].items() if k not in result.get("env", {})}
    if stale:
        result["env"] = {**stale, **result.get("env", {})}
    return result


def _recipe_proxy(recipe) -> str | None:
    return recipe.proxy if recipe and recipe.proxy in catalog.PROXIES else None


def _recipe_info(recipe) -> dict | None:
    if not recipe:
        return None
    return {"needs": list(recipe.needs), "broken": recipe.broken, "proxy": _recipe_proxy(recipe), "args": list(recipe.args),
            "status": recipe.status, "inputs": list(recipe.inputs), "linux": recipe.linux, "optipatcher": recipe.optipatcher,
            "page": recipe.page, "settings": dict(recipe.wiki_settings), "suggestions": dict(recipe.wiki_suggestions),
            "recommended_input": recipe.recommended_input}


def _is_helix(install: dict | None) -> bool:
    return isinstance(install, dict) and install.get("engine") == "helixsr"


def _quality_check(install: dict, facts: dict) -> dict | None:
    """Whether the game asked OptiScaler for its render size, the only way the chosen quality reaches it.

    Judged from the first launch after the quality last changed: the context's render size against the ratio
    Panel wrote. Games that size themselves (Witcher 3 through its FSR) keep their own ratio."""
    ratio = catalog.QUALITY_RATIOS.get((install.get("options") or {}).get("quality") or "")
    seen = facts.get("initial_resolution")
    if ratio is None or not seen or facts.get("stale") or install.get("engine", "optiscaler") != "optiscaler" or _is_helix(install):
        return None
    # The log's clock has whole seconds: a launch in the same second as the change still counts.
    if facts.get("started") is None or float(install.get("quality_at") or install.get("installed_at") or 0) > float(facts["started"]) + 1:
        return None
    render, output = seen["render"][0], seen["output"][0]
    if render <= 0 or output <= 0:
        return None
    observed = output / render
    return {"result": "respected" if abs(observed - ratio) <= ratio * 0.04 else "ignored",
            "input": facts.get("input"), "ratio": round(observed, 2)}


def _facts(install: dict) -> dict:
    if install.get("engine") in ("proton", "dll"):
        return {"present": False, "unverifiable": True}
    if _is_helix(install):
        return helixsr.read_install_log(install)
    return logread.read(Path(install["target"]), since=diagnostics.verification_since(install))


def _verdict(install: dict, facts: dict) -> str:
    if install.get("engine") == "dll":
        return "not_run"
    if install.get("engine") == "proton":
        return "pending"
    return helixsr.verdict(facts) if _is_helix(install) else logread.verdict(facts)


def _requested_fg(solution, choice):
    plan = solution_plan.requested_fg(solution, choice)
    if choice.get("fg") == "on" and plan is None:
        raise UpscalerError("fg_route_unavailable")
    return plan


def _build_solution(gpu, analysis, recipe, build, automatic, blocked):
    effective = catalog.for_game(build, analysis.get("inputs", {}), gpu, recipe)
    generation = catalog.ASSETS[effective.archive].generation if effective.archive else 9
    result = solution_plan.resolve(gpu, analysis, recipe, generation, build.engine, dependencies_ready=bool(automatic))
    if build.engine == "optiscaler" and blocked:
        result["blocked_reason"] = "recipe_unresolved"
    return result


def _generation(install: dict | None) -> int:
    install = install or {}
    build = catalog.BUILDS.get(str(install.get("build")))
    archive = catalog.ASSETS.get(str(install.get("archive") or (build.archive if build else "")))
    return archive.generation if archive else 9


def _archive_sources(archive: Path, generation: int) -> dict[str, Path]:
    """Files of an unpacked OptiScaler release keyed by where they go relative to the exe folder."""
    sources: dict[str, Path] = {}
    for item in archive.iterdir():
        if item.is_file() and item.name not in _JUNK and not item.name.startswith(("!", ".")):
            sources[item.name] = item
    folders = ("OptiScaler",) if generation >= 10 else _ARCHIVE_DIRS
    for directory in folders:
        for item in (archive / directory).rglob("*"):
            if item.is_file() and item.suffix.lower() != ".bat":
                sources[item.relative_to(archive).as_posix()] = item
    return sources


def _wrote_ini(install: dict) -> None:
    """What Panel just left in OptiScaler.ini, so a report can tell a later rewrite (the game, OptiScaler's own
    menu, the user) from a setting Panel never saved."""
    written = diagnostics.ini_values(Path(install["target"]) / "OptiScaler.ini", install.get("edited"))
    install["ini_written"] = None if written.get("missing") else {"at": time.time(), "values": written}


def _clean_options(choice: dict) -> dict:
    quality = choice.get("quality")
    sharpness = choice.get("sharpness")
    return {
        "quality": quality if quality in catalog.QUALITY_RATIOS else None,
        "sharpness": sharpness if sharpness in catalog.SHARPNESS else None,
        "fg": "on" if choice.get("fg") == "on" else "off",
        "fg_route": choice.get("fg_route") if choice.get("fg_route") in ("game", "optiscaler") else None,
        "model": choice.get("model") if isinstance(choice.get("model"), str) and choice.get("model") else None,
    }


def _image_overrides(install: dict, text: str) -> dict:
    if not install.get("image_overrides"):
        return {}
    return {key: value for key in image_settings.MANAGED_SHARPNESS_KEYS if (value := ini.read(text, key)) is not None}


def _option_overrides(choice: dict, reset: bool = False) -> dict[str, str]:
    options = _clean_options(choice)
    overrides: dict[str, str] = {}
    ratio = catalog.QUALITY_RATIOS.get(options["quality"] or "")
    if ratio is not None:
        overrides["QualityOverrides.QualityRatioOverrideEnabled"] = "true"
        # DLAA is the game's native-AA mode: without it the chosen quality never applies there.
        for mode in ("DLAA", "UltraQuality", "Quality", "Balanced", "Performance", "UltraPerformance"):
            overrides[f"QualityOverrides.QualityRatio{mode}"] = f"{ratio:.2f}"
    else:
        overrides["QualityOverrides.QualityRatioOverrideEnabled"] = "false"
    sharpness = catalog.SHARPNESS.get(options["sharpness"] or "")
    if sharpness is not None:
        overrides["Sharpness.OverrideSharpness"] = "true"
        overrides["Sharpness.Sharpness"] = f"{sharpness:.2f}"
    elif reset or options["sharpness"] == "off":
        overrides["Sharpness.OverrideSharpness"] = "false"
    return overrides
