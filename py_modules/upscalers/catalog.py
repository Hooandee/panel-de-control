"""Upscaler builds Panel can install, identified by content hash.

A build is the user's "version" choice. Every file it needs is an asset whose
identity is its SHA-256; URLs are interchangeable mirrors, so moving a download
never invalidates an install.
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath

CATALOG_PATH = Path(__file__).resolve().parents[2] / "shared" / "upscalers" / "catalog.json"


class CatalogError(ValueError):
    pass


def _fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise CatalogError("invalid_fields")
    return value


def _unique_keys(pairs):
    if len({key for key, _ in pairs}) != len(pairs):
        raise CatalogError("duplicate_key")
    return dict(pairs)


def _read(path: Path = CATALOG_PATH) -> dict:
    """The neutral build catalog the Windows app reads too, straight from the same JSON file."""
    raw = _fields(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys),
                  ("schema_version", "archives", "gpu_groups", "preferred", "quality_ratios", "easy_modes", "sharpness",
                   "proxies", "base_ini", "ffx_loader", "assets", "builds"), ("notes",))
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise CatalogError("unsupported_schema")
    return raw


_RAW = _read()
_ARCHIVE_ROLES = ("optiscaler", "optiscaler_beta", "lsfg", "helixsr", "optipatcher")
_ARCHIVES = _fields(_RAW["archives"], _ARCHIVE_ROLES)
OPTISCALER_ARCHIVE = _ARCHIVES["optiscaler"]
OPTISCALER_BETA = _ARCHIVES["optiscaler_beta"]
LSFG_ARCHIVE = _ARCHIVES["lsfg"]
HELIXSR_ARCHIVE = _ARCHIVES["helixsr"]
OPTIPATCHER = _ARCHIVES["optipatcher"]


@dataclass(frozen=True)
class Asset:
    id: str
    filename: str
    sha256: str
    size: int
    urls: tuple[str, ...]
    archive: bool = False
    member: str | None = None
    generation: int = 9


@dataclass(frozen=True)
class Build:
    id: str
    family: str
    version: str
    gpus: tuple[str, ...]
    image: int
    cost: int
    assets: tuple[str, ...] = ()
    replace: dict[str, str] = field(default_factory=dict)
    ini: dict[str, str] = field(default_factory=dict)
    injector: str | None = None
    available: bool = True
    archive: str = OPTISCALER_ARCHIVE
    channel: str = "stable"
    extra_dir: str = ""
    # (model id, INI overrides); the first one is the default.
    models: tuple[tuple[str, dict[str, str]], ...] = ()
    # "helixsr" builds go through HelixSR's own bridge; `way` is its route (only the FSR drop-in).
    engine: str = "optiscaler"
    way: str = ""
    legacy_replace: dict[str, str] = field(default_factory=dict)


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise CatalogError(reason)


def _text(value) -> str:
    _check(isinstance(value, str) and bool(value), "invalid_text")
    return value


def _strings(value) -> tuple[str, ...]:
    _check(isinstance(value, list) and all(isinstance(item, str) and item for item in value), "invalid_list")
    return tuple(value)


def _mapping(value, kinds=(str,)) -> dict:
    _check(isinstance(value, dict) and all(isinstance(item, kinds) and type(item) is not bool for item in value.values()), "invalid_mapping")
    return dict(value)


def _asset(item) -> Asset:
    item = _fields(item, ("id", "filename", "sha256", "size", "urls"), ("archive", "member", "generation", "note"))
    _check(type(item["size"]) is int and item["size"] > 0 and type(item.get("generation", 9)) is int, "invalid_asset")
    _check(type(item.get("archive", False)) is bool and isinstance(item.get("member", ""), str), "invalid_asset")
    _check(isinstance(item["sha256"], str) and len(item["sha256"]) == 64 and set(item["sha256"]) <= set("0123456789abcdef"), "invalid_sha256")
    return Asset(_text(item["id"]), _text(item["filename"]), item["sha256"], item["size"], _strings(item["urls"]),
                 item.get("archive", False), item.get("member"), item.get("generation", 9))


def _build(item) -> Build:
    item = _fields(item, ("id", "family", "version", "engine", "gpus", "image", "cost", "archive"),
                   ("way", "channel", "available", "extra_dir", "assets", "injector", "replace", "legacy_replace",
                    "ini", "models", "note"))
    _check(type(item["image"]) is int and type(item["cost"]) is int and type(item.get("available", True)) is bool, "invalid_build")
    _check(all(isinstance(item.get(key, ""), str) for key in ("channel", "extra_dir", "way"))
           and isinstance(item.get("injector", ""), str), "invalid_build")
    models = item.get("models", [])
    _check(isinstance(models, list), "invalid_models")
    return Build(
        _text(item["id"]), _text(item["family"]), _text(item["version"]), _strings(item["gpus"]), item["image"], item["cost"],
        assets=_strings(item.get("assets", [])), replace=_mapping(item.get("replace", {})), ini=_mapping(item.get("ini", {})),
        injector=item.get("injector"), available=item.get("available", True), archive=_text(item["archive"]),
        channel=item.get("channel", "stable"), extra_dir=item.get("extra_dir", ""),
        models=tuple((_text(model["id"]), _mapping(model["ini"])) for model in (_fields(m, ("id", "ini")) for m in models)),
        engine=_text(item["engine"]), way=item.get("way", ""), legacy_replace=_mapping(item.get("legacy_replace", {})),
    )


def _parse(raw: dict) -> dict:
    groups = _fields(raw["gpu_groups"], ("amd", "every"))
    archives = _fields(raw["archives"], _ARCHIVE_ROLES)
    _check(all(isinstance(value, str) and value for value in archives.values()), "invalid_archives")
    assets = {asset.id: asset for asset in map(_asset, raw["assets"])}
    builds = {build.id: build for build in map(_build, raw["builds"])}
    _check(len(assets) == len(raw["assets"]) and len(builds) == len(raw["builds"]), "duplicate_id")
    for build in builds.values():
        referenced = (*build.assets, *build.replace.values(), *build.legacy_replace.values(), build.archive,
                      *((build.injector,) if build.injector else ()))
        _check(all(asset_id in assets for asset_id in referenced), "missing_asset")
    _check(set(archives.values()) <= assets.keys(), "missing_asset")
    preferred = _mapping(raw["preferred"])
    _check(set(preferred.values()) <= builds.keys(), "missing_build")
    _check(isinstance(raw["ffx_loader"], str) and raw["ffx_loader"], "invalid_ffx_loader")
    return {
        "amd": _strings(groups["amd"]), "every_gpu": _strings(groups["every"]),
        "assets": assets, "builds": builds, "preferred": preferred,
        "quality_ratios": _mapping(raw["quality_ratios"], (int, float)), "easy_modes": _mapping(raw["easy_modes"]),
        "sharpness": _mapping(raw["sharpness"], (int, float, type(None))), "proxies": _strings(raw["proxies"]),
        "base_ini": _mapping(raw["base_ini"]), "ffx_loader": raw["ffx_loader"],
    }


_DATA = _parse(_RAW)
ASSETS: dict[str, Asset] = _DATA["assets"]
AMD = _DATA["amd"]
EVERY_GPU = _DATA["every_gpu"]
BUILDS: dict[str, Build] = _DATA["builds"]
PREFERRED = _DATA["preferred"]
QUALITY_RATIOS = _DATA["quality_ratios"]
EASY_MODES = _DATA["easy_modes"]
SHARPNESS = _DATA["sharpness"]
PROXIES = _DATA["proxies"]
BASE_INI = _DATA["base_ini"]
FFX_LOADER = _DATA["ffx_loader"]


def for_game(build: Build, inputs: dict, gpu: str, recipe=None) -> Build:
    """The build as this game needs it. OptiScaler 0.9 never sees FSR calls made through the FidelityFX SDK 2
    loader (Witcher 3 kept its own FSR 3.1 on an MSI Claw), so XeSS, and FSR 3.1 away from AMD, move to 10 there."""
    if build.id == "fsr-4.1.1" and any(dep.startswith("luma-") for dep in getattr(recipe, "dependencies", ())):
        return replace(build, archive=OPTISCALER_BETA, extra_dir="OptiScaler", ini={
            "Upscalers.Dx12Upscaler": "ffx", "Upscalers.Dx11Upscaler": "ffx_12",
            "Upscalers.VulkanUpscaler": "ffx_12", "FSR.Fsr4GpuSupport": "2", "FSR.UpscalerIndex": "1",
        })
    if build.archive != OPTISCALER_ARCHIVE or not (build.id == "xess" or (build.id == "fsr-3.1" and gpu not in AMD)):
        return build
    if not any(PurePosixPath(str(path)).name.lower() == FFX_LOADER for path in inputs.get("fsr31", ())):
        return build
    # The loader only hands the game's FSR to OptiScaler when OptiScaler offers an FSR 4 model it prefers; with
    # `auto` on a GPU without FSR 4 nothing is offered and the game's FSR 3.1 runs untouched (MSI Claw, Witcher 3).
    ini = {key: value for key, value in build.ini.items() if key != "FSR.Fsr4Update"}
    if ini.get("Upscalers.VulkanUpscaler") == "fsr31":
        ini["Upscalers.VulkanUpscaler"] = "ffx"
    return replace(build, archive=OPTISCALER_BETA, extra_dir="OptiScaler", ini={**ini, "FSR.Fsr4GpuSupport": "4"})


def preferred_build(gpu: str, recipe=None) -> str:
    recommended = BUILDS.get(getattr(recipe, "recommended_build", None))
    if recommended and recommended.available and gpu in recommended.gpus:
        return recommended.id
    return PREFERRED.get(gpu, "fsr-3.1")


def build_supported(build: Build, gpu: str, device: str = "") -> bool:
    if build.id == "fsr-4.1.2-lite-igpu-dll":
        return gpu == "rdna3" and device in ("rog_ally", "rog_ally_x", "legion_go", "legion_go_s")
    if build.id == "fsr-4.1.2-dll" and device in ("steam_deck_lcd", "steam_deck_oled"):
        return False
    return gpu in build.gpus


def build_assets(build: Build) -> list[Asset]:
    if build.engine == "dll":
        return [ASSETS[asset_id] for asset_id in dict.fromkeys((*build.assets, *build.replace.values(), *build.legacy_replace.values()))]
    if build.engine == "helixsr":
        return [ASSETS[build.archive]]
    if build.engine == "proton":
        return []
    ids = [build.archive, *build.assets, *build.replace.values()]
    if build.injector:
        ids.append(build.injector)
    return [ASSETS[asset_id] for asset_id in dict.fromkeys(ids)]


def model_overrides(build: Build | None, model: str | None) -> dict[str, str]:
    if not build or not build.models:
        return {}
    return dict(next((ini for name, ini in build.models if name == model), build.models[0][1]))


# AMD's FP8 SDK providers ship their own FSR 3.1.6 and use it when the GPU can't run FP8 FSR 4 (seen on the Ally).
_FP8_SDK = frozenset({"fsr-4.1.2-dll", "fsr-4.1.1-dll"})


def may_fallback(build: Build, gpu: str) -> str | None:
    return "3.1.6" if build.id in _FP8_SDK and gpu != "rdna4" else None


def describe(gpu: str, device: str = "") -> list[dict]:
    return [
        {
            "id": build.id,
            "family": build.family,
            "version": build.version,
            "image": build.image,
            "cost": build.cost,
            "available": build.available,
            "channel": build.channel,
            "supported": build_supported(build, gpu, device),
            "download_bytes": sum({asset.sha256: asset.size for asset in build_assets(build)}.values()) if build.available else 0,
            "models": [model for model, _ in build.models],
            "dll_names": list(build.replace) if build.engine == "dll" else [],
            "dll_legacy_names": list(build.legacy_replace) if build.engine == "dll" else [],
            "engine": build.engine,
            "way": build.way or None,
            "may_fallback": may_fallback(build, gpu),
        }
        for build in BUILDS.values()
    ]


def fg_routes(gpu: str, inputs: dict, apis: list | tuple = (), streamline: int | None = None, generation: int = 9) -> dict:
    """Every frame generation path this game, GPU and OptiScaler generation can take.

    The OptiScaler wiki ranks DLSSG via Streamline first, then the game's FSR/Xe FG, then OptiFG.
    0.9 only reads DLSSG through Streamline 2+, so Streamline 1 games go through Nukem's there;
    v10 hooks Streamline 1 itself. OptiFG and XeFG are DX12 only.
    """
    output = "xefg" if gpu == "intel" else "fsrfg"
    dx12 = not apis or "d3d12" in apis
    candidates = []
    if "dlssg" in inputs:
        if generation >= 10:
            candidates.append({"input": "dlssg", "output": output, "follows_game": (streamline or 0) >= 2})
        elif (streamline or 0) >= 2:
            candidates.append({"input": "dlssg", "output": output, "follows_game": False})
        else:
            candidates.append({"input": "nukems", "output": "nukems", "follows_game": False})
    native = []
    if "fsrfg" in inputs and dx12:
        native.append({"input": "fsrfg", "output": output, "follows_game": False})
    if "xefg" in inputs and dx12 and generation >= 10:
        native.insert(0 if gpu == "intel" else len(native), {"input": "xefg", "output": output, "follows_game": False})
    # Off NVIDIA, DLSSG only appears through spoofing the game may refuse (Witcher 3 resets DLSSGMode);
    # the game's own FSR/Xe generator needs no spoofing.
    candidates = native + candidates if gpu != "nvidia" else candidates + native
    game = candidates[0] if candidates else None
    if game and output == "xefg" and not dx12:
        game = {**game, "output": "fsrfg"}
    routes = {}
    if game:
        routes["game"] = {**game, "source": "game", "experimental": False}
    if dx12:
        routes["optiscaler"] = {"input": "upscaler", "output": output, "follows_game": False,
                                "source": "optiscaler", "experimental": True}
    return routes


def fg_plan(gpu: str, inputs: dict, recipe_fg: dict | None = None, generation: int = 9,
            apis: list | tuple = (), streamline: int | None = None, route: str | None = None) -> dict | None:
    routes = fg_routes(gpu, inputs, apis, streamline, generation)
    if recipe_fg and generation == 9:
        routes["game"] = {"input": recipe_fg["input"], "output": recipe_fg.get("output", "fsrfg"),
                          "follows_game": False, "source": "game", "experimental": False}
    if not routes:
        return None
    name = route if route in routes else ("game" if "game" in routes else "optiscaler")
    return {**routes[name], "route": name, "routes": routes}


def fg_route_plan(plan: dict | None, route: str | None) -> dict | None:
    """The stored plan switched to another of its routes, without re-scanning the game."""
    if not plan or route not in (plan.get("routes") or {}):
        return plan
    return {**plan["routes"][route], "route": route, "routes": plan["routes"]}


def fg_overrides(plan: dict | None, enabled: bool) -> dict[str, str]:
    if not enabled or not plan:
        return {"FrameGen.Enabled": "false", "FrameGen.FGInput": "nofg", "FrameGen.FGOutput": "nofg"}
    enabled = "auto" if plan.get("follows_game") else "true"
    overrides = {"FrameGen.Enabled": enabled, "FrameGen.FGInput": plan["input"], "FrameGen.FGOutput": plan["output"]}
    if plan["input"] == "upscaler":
        overrides["OptiFG.HUDFix"] = "true"
    return overrides
