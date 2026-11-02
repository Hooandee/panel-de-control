"""Per-game OptiScaler installs: plan, apply with a hashed manifest, verify, undo."""

import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from json_store import atomic_json_save

from . import catalog, games, ini, logread
from .assets import AssetCache, AssetError, sha256

HISTORY_LIMIT = 20
_JUNK = {"setup_linux.sh", "setup_windows.bat"}
_ARCHIVE_DIRS = ("D3D12_Optiscaler",)
_GENERATED = ("OptiScaler.log",)


class UpscalerError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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


def _proxy_override(proxy: str) -> str:
    return f"{proxy.removesuffix('.dll')}=n,b"


class UpscalerService:
    def __init__(self, home: str, state_dir: str, gpu: str, logger=None, proc: str = "/proc", drm: str = "/sys/class/drm"):
        self.home = home
        self.gpu = gpu
        self.logger = logger
        self.proc = proc
        self.drm = drm
        self.state_path = Path(state_dir) / "state.json"
        self.cache = AssetCache(Path(state_dir) / "cache")
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
        }

    def _status(self, install: dict, entry: dict) -> str:
        target = Path(install.get("target", ""))
        proxy = install.get("proxy") or ""
        if not (target / games.MANIFEST_DIR / "manifest.json").is_file() or not (target / proxy).is_file():
            return "broken"
        history = entry.get("history") or []
        return history[-1].get("result", "pending") if history else "pending"

    def compatibility(self, appids: list[str]) -> dict[str, bool]:
        """Which games ship an upscaler Panel can replace, cached by install folder mtime."""
        result = {}
        for appid in appids[:400]:
            installed = games.find_installed(self.home, str(appid))
            if installed is None:
                continue
            try:
                stamp = installed.root.stat().st_mtime
            except OSError:
                continue
            cached = self._compat.get(installed.appid)
            if cached is None or cached[0] != stamp:
                cached = (stamp, games.ships_upscaler(installed.root))
                self._compat[installed.appid] = cached
            result[installed.appid] = cached[1]
        return result

    def game(self, appid: str) -> dict:
        installed = games.find_installed(self.home, appid)
        if installed is None:
            raise UpscalerError("not_installed")
        entry = self._game_state(appid)
        analysis = games.analyze(installed.root, entry.get("exe"))
        install = entry.get("install")
        return {
            "appid": appid,
            "name": installed.name,
            "updating": installed.state_flags != games.STATE_FULLY_INSTALLED,
            "analysis": analysis,
            "install": {**install, "status": self._status(install, entry)} if isinstance(install, dict) else None,
            "history": entry.get("history", [])[-HISTORY_LIMIT:],
            "override": _proxy_override(install["proxy"]) if isinstance(install, dict) else None,
        }

    def set_exe(self, appid: str, exe: str | None) -> dict:
        installed = games.find_installed(self.home, appid)
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
        installed = games.find_installed(self.home, appid)
        if installed is None:
            raise UpscalerError("not_installed")
        if installed.state_flags != games.STATE_FULLY_INSTALLED:
            raise UpscalerError("updating")
        if games.running_under(installed.root, self.proc):
            raise UpscalerError("running")
        analysis = games.analyze(installed.root, self._game_state(appid).get("exe"))
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
        proxy = str(choice.get("proxy") or "dxgi.dll")
        if proxy not in catalog.PROXIES:
            raise UpscalerError("invalid_proxy")

        installed, analysis, target = self._guard(appid, bool(choice.get("confirm_anti_cheat")))
        entry = self._game_state(appid)
        if isinstance(entry.get("install"), dict):
            self._remove(Path(entry["install"]["target"]))
            entry["install"] = None
        if analysis["foreign"]:
            raise UpscalerError("foreign")

        assets = catalog.build_assets(build)
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
        archive = paths[catalog.OPTISCALER_ARCHIVE]
        sources: dict[str, Path] = {}
        for item in archive.iterdir():
            if item.is_file() and item.name not in _JUNK and not item.name.startswith(("!", ".")):
                sources[item.name] = item
        for directory in _ARCHIVE_DIRS:
            for item in (archive / directory).rglob("*"):
                if item.is_file():
                    sources[item.relative_to(archive).as_posix()] = item
        base_ini = sources.pop("OptiScaler.ini").read_text(encoding="utf-8", errors="replace")
        injector = sources.pop("OptiScaler.dll")
        if build.injector:
            injector = paths[build.injector]
        sources[proxy] = injector
        for name, asset_id in build.replace.items():
            sources[name] = paths[asset_id]
        for asset_id in build.assets:
            sources[catalog.ASSETS[asset_id].filename] = paths[asset_id]

        overrides = {**catalog.BASE_INI, **build.ini, **_option_overrides(choice)}
        manifest = self._apply(target, sources, ini.apply(base_ini, overrides))

        now = time.time()
        entry["install"] = {
            "build": build.id, "proxy": proxy, "target": str(target), "exe": analysis["exe"],
            "installed_at": now, "options": _clean_options(choice),
        }
        entry["history"].append({
            "build": build.id, "proxy": proxy, "at": now, "result": "pending", "exe": analysis["exe"],
        })
        entry["history"] = entry["history"][-HISTORY_LIMIT:]
        self._save()
        return {"files": len(manifest["files"]), "override": _proxy_override(proxy)}

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
        installed = games.find_installed(self.home, appid)
        if installed and games.running_under(installed.root, self.proc):
            raise UpscalerError("running")
        path = Path(install["target"]) / "OptiScaler.ini"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raise UpscalerError("broken") from None
        path.write_text(ini.apply(text, _option_overrides(choice, reset=True)), encoding="utf-8")
        install["options"] = _clean_options(choice)
        self._save()
        return {"options": install["options"]}

    def uninstall(self, appid: str) -> dict:
        entry = self._game_state(appid)
        install = entry.get("install")
        if not isinstance(install, dict):
            raise UpscalerError("not_patched")
        installed = games.find_installed(self.home, appid)
        if installed and games.running_under(installed.root, self.proc):
            raise UpscalerError("running")
        self._update_job(phase="restore")
        kept = self._remove(Path(install["target"]))
        override = _proxy_override(install["proxy"])
        entry["install"] = None
        self._save()
        return {"kept": kept, "override": override}

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

    def verify(self, appid: str) -> dict:
        entry = self._game_state(appid)
        install = entry.get("install")
        if not isinstance(install, dict):
            raise UpscalerError("not_patched")
        facts = logread.read(Path(install["target"]), since=install.get("installed_at"))
        result = logread.verdict(facts)
        if self._status(install, entry) == "broken":
            result = "broken"
        history = entry.get("history") or []
        if history and history[-1].get("build") == install.get("build") and result != "not_run":
            history[-1]["result"] = result
            history[-1]["facts"] = {k: facts[k] for k in ("upscaler", "fsr4", "resolution", "version") if k in facts}
            self._save()
        return {"result": result, "facts": facts}

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


def _clean_options(choice: dict) -> dict:
    quality = choice.get("quality")
    sharpness = choice.get("sharpness")
    return {
        "quality": quality if quality in catalog.QUALITY_RATIOS else None,
        "sharpness": sharpness if sharpness in catalog.SHARPNESS else None,
    }


def _option_overrides(choice: dict, reset: bool = False) -> dict[str, str]:
    options = _clean_options(choice)
    overrides: dict[str, str] = {}
    ratio = catalog.QUALITY_RATIOS.get(options["quality"] or "")
    if ratio is not None:
        overrides["QualityOverrides.QualityRatioOverrideEnabled"] = "true"
        for mode in ("UltraQuality", "Quality", "Balanced", "Performance", "UltraPerformance"):
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
