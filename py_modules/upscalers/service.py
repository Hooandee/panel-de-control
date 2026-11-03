"""Per-game OptiScaler installs: plan, apply with a hashed manifest, verify, undo."""

import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from json_store import atomic_json_save

from . import capture, catalog, diagnostics, games, helixsr, identify, ini, keys, launchers, logread, lsfg, recipes, wiki
from .assets import AssetCache, AssetError, sha256

HISTORY_LIMIT = 20
_JUNK = {"setup_linux.sh", "setup_windows.bat"}
_ARCHIVE_DIRS = ("D3D12_Optiscaler",)
_GENERATED = ("OptiScaler.log",)
HELIX_MARKER = "helixsr.json"
# Proton's own FSR 4 switch: the official name and the per-GPU names custom builds keep.
PROTON_FSR4_ENVS = ("FSR4_UPGRADE", "PROTON_FSR4_UPGRADE", "PROTON_FSR4_RDNA3_UPGRADE")
# What HelixSR's bridge leaves in the game for each way; gone means a game update or verify removed it.
HELIX_INSTALL_FILE = "helixsr-install.json"


# Native Linux games run without Proton; OptiScaler only hooks Windows executables.
NATIVE_ANALYSIS = {
    "candidates": [], "exe": None, "apis": [], "manual": False, "target": None,
    "inputs": {}, "anti_cheat": False, "foreign": False,
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
    def __init__(self, home: str, state_dir: str, gpu: str, logger=None, proc: str = "/proc", drm: str = "/sys/class/drm"):
        self.home = home
        self.gpu = gpu
        self.logger = logger
        self.proc = proc
        self.drm = drm
        self.search = identify.store_search
        self.press = keys.press
        self.state_path = Path(state_dir) / "state.json"
        self.cache = AssetCache(Path(state_dir) / "cache")
        self.lsfg = lsfg.Lsfg(home, Path(state_dir))
        self.helix = helixsr.HelixSR(home)
        self.wiki = wiki.WikiCache(Path(state_dir))
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
        return {"games": games_state if isinstance(games_state, dict) else {}}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json_save(str(self.state_path), self.state)

    def _game_state(self, appid: str) -> dict:
        entry = self.state["games"].setdefault(appid, {})
        entry.setdefault("history", [])
        return entry

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
                }
        return {
            "gpu": self.gpu,
            "display": panel_resolution(self.drm),
            "preferred": catalog.preferred_build(self.gpu),
            "builds": catalog.describe(self.gpu),
            "cached": [a.id for a in catalog.ASSETS.values() if self.cache.ready(a)],
            "installs": installs,
            "job": self.job(),
            "helixsr": {"downloaded": self.helix.ready()},
        }

    def _status(self, install: dict, entry: dict) -> str:
        target = Path(install.get("target", ""))
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
            result[installed.appid] = cached[1]
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
        steam_appid = identity.get("steam_appid") if identity else None
        recipe = recipes.recipe_for(str(steam_appid)) if steam_appid else recipes.recipe_for(appid)
        if recipe is None and installed is not None:
            found = self.wiki.lookup(identity.get("name") if identity else None, installed.name)
            recipe = recipes.from_facts(str(appid), found, "optiscaler-wiki@live") if found else None
        return recipes.with_engine(recipe, appid, installed.root) if installed else recipe

    def refresh_wiki(self) -> dict:
        return self.wiki.refresh()

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
        return {
            "appid": appid,
            "name": installed.name,
            "updating": games.update_state(installed.state_flags),
            "shortcut": installed.shortcut,
            "native": installed.native,
            "launcher": installed.launcher[0] if installed.launcher else None,
            "identity": identity,
            "analysis": analysis,
            "install": {**install, "status": self._status(install, entry)} if isinstance(install, dict) else None,
            "history": entry.get("history", [])[-HISTORY_LIMIT:],
            "recipe": recipes.applies(recipe),
            "recipe_info": _recipe_info(recipe),
            "foreign_backup": {"at": entry["foreign_backup"]["at"]} if isinstance(entry.get("foreign_backup"), dict) else None,
            "fg_note": recipe.fg_note if recipe else None,
            "fg_plan": None if installed.native or _is_helix(install) else _fg_plan(self.gpu, analysis, recipe, _generation(install),
                                                             (install or {}).get("options", {}).get("fg_route")),
        }

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
        if not catalog.build_supported(build, self.gpu) and not choice.get("force"):
            raise UpscalerError("unsupported_gpu")
        if build.engine == "helixsr":
            return self._install_helix(appid, build, choice)
        if build.engine == "proton":
            return self._install_proton(appid, build, choice)
        if choice.get("proxy") and str(choice["proxy"]) not in catalog.PROXIES:
            raise UpscalerError("invalid_proxy")

        installed, analysis, target = self._guard(appid, bool(choice.get("confirm_anti_cheat")))
        entry = self._game_state(appid)
        left = self._replace(entry, installed)
        if left is not None:
            analysis = games.analyze(installed.root, entry.get("exe"), analysis["exe"])
        if analysis["foreign"]:
            raise UpscalerError("foreign")

        recipe = self._recipe(appid, entry.get("identity"), installed)
        proxy = str(choice.get("proxy") or _recipe_proxy(recipe) or "dxgi.dll")
        assets = catalog.build_assets(build)
        if recipe:
            assets += [catalog.ASSETS[a] for a in dict.fromkeys(recipe.files.values()) if catalog.ASSETS[a] not in assets]
            if recipe.optipatcher:
                assets.append(catalog.ASSETS[catalog.OPTIPATCHER])
        total = sum(asset.size for asset in assets)
        self._update_job(phase="download", total=total, done=0)
        paths: dict[str, Path] = {}
        offset = 0
        for asset in assets:
            base = offset
            paths[asset.id] = self.cache.ensure(
                asset, lambda received, base=base: self._update_job(done=base + received), self._cancel.is_set
            )
            offset += asset.size
            self._update_job(done=offset)

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

        fg_plan = _fg_plan(self.gpu, analysis, recipe, archive_asset.generation, choice.get("fg_route"))
        overrides = {
            **catalog.BASE_INI, **build.ini, **(recipe.ini if recipe else {}), **_option_overrides(choice),
            **({"Plugins.LoadAsiPlugins": "true"} if recipe and recipe.optipatcher else {}),
            **catalog.model_overrides(build, choice.get("model")),
            **catalog.fg_overrides(fg_plan, choice.get("fg") == "on"),
        }
        manifest = self._apply(target, sources, ini.apply(base_ini, overrides))
        managed = sorted(overrides)

        now = time.time()
        entry["install"] = {
            "build": build.id, "proxy": proxy, "target": str(target), "exe": analysis["exe"],
            "installed_at": now, "options": _clean_options(choice),
            "native_dlls": list(recipe.native_dlls) if recipe else [],
            "fg_plan": fg_plan,
            "managed": managed,
            "args": list(recipe.args) if recipe else [],
            "added_args": [],
        }
        entry["history"].append({
            "build": build.id, "proxy": proxy, "at": now, "result": "pending", "exe": analysis["exe"],
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

    def _install_helix(self, appid: str, build: catalog.Build, choice: dict) -> dict:
        installed, analysis, target = self._guard(appid, bool(choice.get("confirm_anti_cheat")))
        if build.way == "fsr" and "fsr31" not in analysis["inputs"]:
            raise UpscalerError("helixsr_no_fsr")
        entry = self._game_state(appid)
        left = self._replace(entry, installed)
        if left is not None:
            analysis = games.analyze(installed.root, entry.get("exe"), analysis["exe"])
        if analysis["foreign"]:
            raise UpscalerError("foreign")

        if not self.helix.ready():
            asset = catalog.ASSETS[build.archive]
            self._update_job(phase="download", total=asset.size, done=0)
            archive = self.cache.ensure(asset, lambda received: self._update_job(done=received), self._cancel.is_set)
            self._update_job(phase="unpack")
            self._helix("unpack", archive)
            shutil.rmtree(archive.parent, ignore_errors=True)
        self._update_job(phase="copy")
        game = self._helix("install", installed.root)
        exe_folder = Path(game.get("exe_folder") or target)
        options = _clean_options({**choice, "fg": "off"})
        log = Path(game["log_path"]) if game.get("log_path") else exe_folder / "helixsr.log"
        meta = target / games.MANIFEST_DIR
        meta.mkdir(exist_ok=True)
        atomic_json_save(str(meta / HELIX_MARKER), {"way": build.way, "release": helixsr.RELEASE})
        _own_like(target, [meta])

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
        self._drop(old, installed.root)
        if old.get("launcher"):
            self._launcher_overrides(installed, old, remove=True)
        entry["install"] = None
        return {
            "overrides": [] if old.get("launcher") else _overrides(old),
            "args": list(old.get("added_args", [])),
            "env": {old["env"]: None} if old.get("engine") == "proton" else {},
        }

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
        self._helix("remove", root)
        log = Path(install.get("log", ""))
        for generated in (log, log.with_name(helixsr.HLX_FSR_LOG)):
            if generated.name and generated.is_file():
                generated.unlink()
        shutil.rmtree(Path(install["target"]) / games.MANIFEST_DIR, ignore_errors=True)
        return []

    def _apply(self, target: Path, sources: dict[str, Path], ini_text: str) -> dict:
        meta = target / games.MANIFEST_DIR
        backup = meta / "backup"
        meta.mkdir(exist_ok=True)
        manifest: dict = {"files": {}, "backups": [], "dirs": []}
        try:
            for relative, source in sources.items():
                self._place(target, relative, manifest, backup)
                manifest["files"][relative] = None
                shutil.copyfile(source, target / relative)
                manifest["files"][relative] = sha256(target / relative)
            self._place(target, "OptiScaler.ini", manifest, backup)
            (target / "OptiScaler.ini").write_text(ini_text, encoding="utf-8")
            manifest["files"]["OptiScaler.ini"] = None
            for generated in _GENERATED:
                if (target / generated).exists():
                    self._place(target, generated, manifest, backup)
        except BaseException:
            atomic_json_save(str(meta / "manifest.json"), manifest)
            self._remove(target)
            raise
        atomic_json_save(str(meta / "manifest.json"), manifest)
        _own_like(target, [*(target / f for f in manifest["files"]), *(target / d for d in manifest["dirs"]), meta])
        return manifest

    @staticmethod
    def _place(target: Path, relative: str, manifest: dict, backup: Path) -> None:
        destination = target / relative
        for parent in reversed(Path(relative).parents[:-1]):
            if not (target / parent).exists():
                (target / parent).mkdir()
                manifest["dirs"].append(parent.as_posix())
        if destination.exists() or destination.is_symlink():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            os.replace(destination, saved)
            manifest["backups"].append(relative)

    # ---- options, uninstall, verify -----------------------------------------
    def configure(self, appid: str, choice: dict) -> dict:
        entry = self._game_state(appid)
        install = entry.get("install")
        if not isinstance(install, dict):
            raise UpscalerError("not_patched")
        installed = self._find(appid)
        if installed and games.running_under(installed.root, self.proc):
            raise UpscalerError("running")
        if _is_helix(install) or install.get("engine") == "proton":
            install["options"] = _clean_options({**choice, "fg": "off"})
            self._save()
            return {"options": install["options"]}
        path = Path(install["target"]) / "OptiScaler.ini"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raise UpscalerError("broken") from None
        plan = install.get("fg_plan")
        if installed and not installed.native:
            recipe = self._recipe(appid, self._identity(installed, entry), installed)
            analysis = games.analyze(installed.root, entry.get("exe"), recipe.exe if recipe else installed.exe)
            plan = _fg_plan(self.gpu, analysis, recipe, _generation(install), choice.get("fg_route"))
        install["fg_plan"] = catalog.fg_route_plan(plan, choice.get("fg_route"))
        fg = catalog.fg_overrides(install.get("fg_plan"), choice.get("fg") == "on")
        model = catalog.model_overrides(catalog.BUILDS.get(install.get("build", "")), choice.get("model"))
        path.write_text(ini.apply(text, {**_option_overrides(choice, reset=True), **model, **fg}), encoding="utf-8")
        install["options"] = _clean_options(choice)
        self._save()
        return {"options": install["options"]}

    # ---- another tool's install --------------------------------------------------------------
    def adopt_foreign(self, appid: str) -> dict:
        """Set another tool's OptiScaler or HelixSR aside (kept, restorable) so Panel's can go in cleanly."""
        installed, _analysis, target = self._guard(appid, True)
        entry = self._game_state(appid)
        if isinstance(entry.get("install"), dict):
            raise UpscalerError("still_patched")
        items, swaps = games.foreign_items(target), games.helix_swaps(target)
        if not items and not swaps:
            raise UpscalerError("no_foreign")
        backup = self.state_path.parent / "foreign" / str(appid) / str(int(time.time()))
        backup.mkdir(parents=True, exist_ok=True)
        for name in items:
            shutil.move(str(target / name), str(backup / name))
        for name in swaps:
            original = target / Path(name).with_suffix(".original.dll").name
            if (target / name).exists():
                shutil.move(str(target / name), str(backup / name))
            os.replace(original, target / name)
        entry["foreign_backup"] = {"dir": str(backup), "target": str(target), "items": items, "swaps": swaps,
                                   "at": time.time()}
        self._save()
        return {"moved": [*items, *swaps]}

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
        for name in record.get("swaps", []):
            os.replace(target / name, target / Path(name).with_suffix(".original.dll").name)
            if (backup / name).exists():
                shutil.move(str(backup / name), str(target / name))
        for name in record.get("items", []):
            if (backup / name).exists() and not (target / name).exists():
                shutil.move(str(backup / name), str(target / name))
        shutil.rmtree(backup, ignore_errors=True)
        entry.pop("foreign_backup", None)
        self._save()
        return {"restored": [*record.get("items", []), *record.get("swaps", [])]}

    # ---- advanced: every OptiScaler.ini key ---------------------------------------------------
    def _ini_path(self, appid: str) -> tuple[dict, Path]:
        install = self._game_state(appid).get("install")
        if not isinstance(install, dict) or install.get("engine") in ("proton", "helixsr"):
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
        """One key the user changed by hand; Panel's own keys stay Panel's so it never overwrites a choice silently."""
        install, path = self._ini_path(appid)
        value = str(value).strip()
        if not value or len(value) > 200 or any(c in value for c in "\r\n[]"):
            raise UpscalerError("ini_value")
        text = path.read_text(encoding="utf-8", errors="replace")
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
        kept = self._drop(install, installed.root if installed else Path(install["target"]))
        if install.get("launcher") and installed:
            self._launcher_overrides(installed, install, remove=True)
            result = {"kept": kept, "overrides": [], "args": [], "launcher": install["launcher"][0]}
        else:
            result = {"kept": kept, "overrides": _overrides(install), "args": install.get("added_args", [])}
        if install.get("engine") == "proton":
            result["env"] = {install["env"]: None}
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

    def record_added_args(self, appid: str, args: list[str]) -> dict:
        """Remember which launch arguments Panel added, so removal never strips the user's own."""
        install = self._game_state(appid).get("install")
        if not isinstance(install, dict):
            raise UpscalerError("not_patched")
        install["added_args"] = [a for a in args if a in install.get("args", [])]
        self._save()
        return {"added_args": install["added_args"]}

    @staticmethod
    def _remove(target: Path) -> list[str]:
        meta = target / games.MANIFEST_DIR
        try:
            manifest = json.loads((meta / "manifest.json").read_text())
        except (OSError, ValueError):
            return []
        kept = []
        for relative, digest in manifest.get("files", {}).items():
            path = target / relative
            if not path.is_file():
                continue
            if digest is None or sha256(path) == digest:
                path.unlink()
            else:
                kept.append(relative)
        for generated in _GENERATED:
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
        facts = _facts(install)
        generating = bool(facts.get("fg")) and facts.get("fg_state", "true") == "true"
        return {"result": _verdict(install, facts), "resolution": facts.get("resolution"), "fg": generating}

    # ---- lsfg-vk -----------------------------------------------------------------------------
    def lsfg_status(self) -> dict:
        return self.lsfg.status()

    def lsfg_install(self) -> dict:
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
            self.lsfg.uninstall()
            return self.lsfg.restore_foreign()
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

    def press_key(self, appid: str, action: str) -> dict:
        """OptiScaler hotkeys for devices without a keyboard; only while the game runs."""
        install = self._game_state(appid).get("install")
        if not isinstance(install, dict):
            raise UpscalerError("not_patched")
        installed = self._find(appid)
        if installed is None or not games.running_under(installed.root, self.proc):
            raise UpscalerError("not_running")
        try:
            self.press(action)
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
            history[-1]["facts"] = {k: facts[k] for k in ("upscaler", "input", "fg", "resolution", "version") if k in facts}
            self._save()
        return {"result": result, "facts": facts}

    def diagnose(self, appid: str) -> dict:
        return diagnostics.game_report(self.home, str(appid), self._game_state(str(appid)))

    def report(self) -> dict:
        """Bundle section: every game Panel has touched, newest first, explained in full."""
        touched = [
            (appid, entry) for appid, entry in self.state["games"].items()
            if isinstance(entry.get("install"), dict) or entry.get("history") or entry.get("exe")
        ]
        touched.sort(key=lambda item: max([h.get("at", 0) for h in item[1].get("history", [])] or [0]), reverse=True)
        return {
            "gpu": self.gpu,
            "environment": diagnostics.environment(),
            "cached_assets": [a.id for a in catalog.ASSETS.values() if self.cache.ready(a)],
            "job": self.job(),
            "lsfg": self.lsfg.status(),
            "helixsr": {"downloaded": self.helix.ready(), "release": helixsr.RELEASE},
            "games": [diagnostics.game_report(self.home, appid, entry) for appid, entry in touched[:12]],
        }

    def support_state(self) -> dict:
        return {
            "gpu": self.gpu,
            "installs": {
                appid: {
                    "build": entry["install"].get("build"),
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
    return {"needs": list(recipe.needs), "broken": recipe.broken, "proxy": _recipe_proxy(recipe), "args": list(recipe.args)}


def _own_like(folder: Path, paths: list[Path]) -> None:
    """Steam updates and verifies games as the user, so nothing Panel leaves in a game folder may stay root's."""
    if os.geteuid() != 0:
        return
    try:
        stat = folder.stat()
    except OSError:
        return
    for path in paths:
        for item in [path, *(path.rglob("*") if path.is_dir() else ())]:
            try:
                os.chown(item, stat.st_uid, stat.st_gid, follow_symlinks=False)
            except OSError:
                pass


def _is_helix(install: dict | None) -> bool:
    return isinstance(install, dict) and install.get("engine") == "helixsr"


def _facts(install: dict) -> dict:
    if install.get("engine") == "proton":
        return {"present": False, "unverifiable": True}
    if _is_helix(install):
        return helixsr.read_log([Path(install["log"])], since=install.get("installed_at"))
    return logread.read(Path(install["target"]), since=install.get("installed_at"))


def _verdict(install: dict, facts: dict) -> str:
    if install.get("engine") == "proton":
        return "pending"
    return helixsr.verdict(facts) if _is_helix(install) else logread.verdict(facts)


def _fg_plan(gpu: str, analysis: dict, recipe, generation: int, route: str | None) -> dict | None:
    return catalog.fg_plan(gpu, analysis["inputs"], recipe.fg if recipe else None, generation,
                           analysis.get("apis", ()), analysis.get("streamline"), route)


def _generation(install: dict | None) -> int:
    build = catalog.BUILDS.get(str((install or {}).get("build")))
    return catalog.ASSETS[build.archive].generation if build else 9


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


def _option_overrides(choice: dict, reset: bool = False) -> dict[str, str]:
    options = _clean_options(choice)
    overrides: dict[str, str] = {}
    ratio = catalog.QUALITY_RATIOS.get(options["quality"] or "")
    if ratio is not None:
        overrides["QualityOverrides.QualityRatioOverrideEnabled"] = "true"
        # DLAA is the game's native-AA mode: without it the chosen quality never applies there.
        for mode in ("DLAA", "UltraQuality", "Quality", "Balanced", "Performance", "UltraPerformance"):
            overrides[f"QualityOverrides.QualityRatio{mode}"] = f"{ratio:.2f}"
    elif reset:
        overrides["QualityOverrides.QualityRatioOverrideEnabled"] = "false"
    sharpness = catalog.SHARPNESS.get(options["sharpness"] or "")
    if sharpness is not None:
        overrides["Sharpness.OverrideSharpness"] = "true"
        overrides["Sharpness.Sharpness"] = f"{sharpness:.2f}"
    elif reset or options["sharpness"] == "off":
        overrides["Sharpness.OverrideSharpness"] = "false"
    return overrides
