"""What the Escaladores backend would do for every game of a captured library, without playing or downloading.

For each game: how Panel finds it, what `analyze` sees, what `game` and `compatibility` report, the Mako profile
key, and for every build the machine supports the install plan (files and where they come from, OptiScaler.ini
keys, proxy, DLL overrides, launch options, environment) or the error it stops with. Downloads are replaced by
a fake asset cache and nothing is written into the game.
"""

import hashlib
import json
import shutil
from pathlib import Path

from upscalers import catalog, games, prefix_dependencies, recipe_catalog, service as service_module
from upscalers.service import UpscalerError, UpscalerService
from upscalers_corpus_tree import FakeHome

GOLDEN = Path(__file__).parent / "fixtures" / "upscalers_corpus" / "golden"
_OPTISCALER_ROOT = ("OptiScaler.dll", "OptiScaler.ini", "amd_fidelityfx_upscaler_dx12.dll", "libxess.dll",
                    "amd_fidelityfx_vk.dll", "setup_linux.sh")


class FakeAssets:
    """Every catalog asset as a small local file or unpacked folder, laid out like the real release."""

    def __init__(self, base: Path):
        self.base = base

    def path(self, asset: catalog.Asset) -> Path:
        folder = self.base / asset.id
        if not asset.archive:
            target = folder / Path(asset.member or asset.filename).name
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(asset.id.encode())
            return target
        if not folder.is_dir():
            files = []
            if asset.id in (catalog.OPTISCALER_ARCHIVE, catalog.OPTISCALER_BETA) or "optiscaler" in asset.id.lower():
                files += _OPTISCALER_ROOT
                files += ["D3D12_Optiscaler/D3D12Core.dll"] if asset.generation < 10 else [
                    "OptiScaler/amd_fidelityfx_upscaler_dx12.dll", "OptiScaler/libxess.dll", "OptiScaler/D3D12_Optiscaler/D3D12Core.dll"]
            for dependency in recipe_catalog.bundled().dependencies.values():
                if dependency.kind == "game_files" and dependency.asset == asset.id:
                    files += list(dependency.files.values())
            for name in files or [asset.filename]:
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
        return folder

    def label(self, source: Path) -> str:
        try:
            relative = Path(source).relative_to(self.base)
        except ValueError:
            return "generated"
        return f"{relative.parts[0]}:{Path(*relative.parts[1:]).as_posix()}"


def _ini_keys(text: str | None) -> dict[str, str]:
    keys, section = {}, ""
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif "=" in line and not line.startswith(";"):
            key, value = line.split("=", 1)
            keys[f"{section}.{key.strip()}"] = value.strip()
    return keys


def _service(home: FakeHome, state: Path, gpu: str, device: str, assets: FakeAssets, applied: list) -> UpscalerService:
    if state.exists():
        shutil.rmtree(state)
    (state / "proc").mkdir(parents=True)
    (state / "cache").mkdir()
    service = UpscalerService(str(home.home), str(state), gpu, proc=str(state / "proc"), drm=str(state / "drm"), device=device)
    service.search = lambda term: []

    def fetch(wanted, pinned_only=frozenset()):
        unique = {asset.id: asset for asset in wanted}
        return {asset_id: assets.path(asset) for asset_id, asset in unique.items()}, dict(unique)

    def apply(target, sources, ini_text, configuration=None):
        applied.append({"target": str(target), "files": {name: assets.label(path) for name, path in sources.items()},
                        "ini": _ini_keys(ini_text) if ini_text is not None else None,
                        "configuration": configuration or {}})
        return {"files": dict.fromkeys(sources, "")}

    service._fetch_assets = fetch
    service._apply = apply
    service._helix = lambda method, *args: {}
    return service


def _install_plan(service: UpscalerService, appid: str, build: catalog.Build, applied: list) -> dict:
    choice = {"build": build.id, "confirm_anti_cheat": True}
    if build.engine == "proton":
        choice["env"] = "FSR4_UPGRADE"
    applied.clear()
    plan: dict = {}
    try:
        try:
            result = service.install(appid, choice)
        except UpscalerError as error:
            if error.code != "recipe_transaction_required":
                raise
            service.begin_scaler_transition(appid)
            plan["transaction"] = True
            result = service.install(appid, choice)
    except UpscalerError as error:
        return {**plan, "error": error.code}
    install = service.state["games"][appid]["install"]
    plan.update({
        "result": {key: value for key, value in result.items() if key != "files"},
        "applied": applied[-1] if applied else None,
        **{key: install.get(key) for key in (
            "engine", "build", "archive", "proxy", "target", "exe", "dll_targets", "native_dlls", "args", "env",
            "fg_plan", "managed", "menu_key", "reframework_upscaler", "recipe_revision", "recipe_dependencies",
            "recipe_configuration", "windows_components_error", "options") if key in install},
        "components": [item.get("id") for item in install.get("components") or []],
        "overrides": service_module._overrides(install),
    })
    return plan


def _mako_key(service: UpscalerService, home: FakeHome, appid: str) -> dict:
    try:
        key = service._launch_owner(appid, mako_profile=True, claim=False)
    except UpscalerError as error:
        return {"error": error.code}
    if key == appid:
        return {"key": "appid"}
    installed = service._find(appid)
    root = installed.root.resolve()
    exe = str((root / installed.exe).resolve()) if installed.exe else None
    identity = json.dumps([str(root), exe, installed.launcher], separators=(",", ":"))
    return {"key": "launch_identity", "identity": home.tokens([str(root), exe, installed.launcher]),
            "formula": key == str(int(hashlib.sha256(identity.encode()).hexdigest()[:16], 16))}


def machine_plan(base: Path, capture: dict) -> dict:
    """Plan for every game of one capture, keyed by appid."""
    home = FakeHome(base / "fake", capture)
    home.build()
    assets = FakeAssets(base / "assets")
    applied: list = []
    gpu, device = capture["gpu"], capture["device"]
    original_prepare = prefix_dependencies.prepare
    prefix_dependencies.prepare = lambda *args, **kwargs: None
    try:
        plans = {}
        for game in capture["games"]:
            appid = game["appid"]
            if appid in plans:
                continue
            reader = _service(home, base / "state", gpu, device, assets, applied)
            plans[appid] = _game_plan(reader, home, appid, game)
            if plans[appid].get("found") is None:
                continue
            installs = {}
            for build in catalog.BUILDS.values():
                if not build.available or not catalog.build_supported(build, gpu, device):
                    continue
                writer = _service(home, base / "state", gpu, device, assets, applied)
                installs[build.id] = _install_plan(writer, appid, build, applied)
                installed = writer._find(appid)
                if installed is not None:
                    for meta in installed.root.rglob(games.MANIFEST_DIR):
                        shutil.rmtree(meta, ignore_errors=True)
            plans[appid]["installs"] = installs
        return home.tokens(plans)
    finally:
        prefix_dependencies.prepare = original_prepare


def _game_plan(service: UpscalerService, home: FakeHome, appid: str, game: dict) -> dict:
    plan: dict = {"name": game.get("name"), "kind": game["kind"]}
    installed = service._find(appid)
    if installed is None:
        plan["found"] = None
        return plan
    plan["found"] = {"root": str(installed.root), "exe": installed.exe, "native": installed.native,
                     "shortcut": installed.shortcut, "launcher": list(installed.launcher) if installed.launcher else None,
                     "build_id": installed.build_id, "updating": games.update_state(installed.state_flags)}
    plan["compatibility"] = service.compatibility([appid]).get(appid)
    plan["mako_profile"] = _mako_key(service, home, appid)
    try:
        detail = service.game(appid)
    except UpscalerError as error:
        plan["game"] = {"error": error.code}
        return plan
    plan["analysis"] = detail["analysis"]
    plan["game"] = {key: detail.get(key) for key in (
        "preferred", "recipe", "recipe_info", "identity", "fg_note", "fg_plan", "solution", "solutions")}
    return plan


def golden_path(machine: str) -> Path:
    return GOLDEN / f"{machine}.json"


def dump(plan: dict) -> str:
    return json.dumps(plan, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
