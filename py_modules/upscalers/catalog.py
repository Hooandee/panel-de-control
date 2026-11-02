"""Upscaler builds Panel can install, identified by content hash.

A build is the user's "version" choice. Every file it needs is an asset whose
identity is its SHA-256; URLs are interchangeable mirrors, so moving a download
never invalidates an install.
"""

from dataclasses import dataclass, field

OPTISCALER_ARCHIVE = "optiscaler-0.9.4"
OPTISCALER_BETA = "optiscaler-10-nightly"


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


_BLEEDING = "https://github.com/xXJSONDeruloXx/OptiScaler-Bleeding-Edge/releases/download"

ASSETS: dict[str, Asset] = {
    asset.id: asset
    for asset in (
        Asset(
            OPTISCALER_ARCHIVE,
            "Optiscaler_0.9.4-final.20260718._MM.7z",
            "575cb4df866116093df75af607e37fd70e10f5163e0f23fd5c804142e80ef0ad",
            55016448,
            ("https://github.com/optiscaler/OptiScaler/releases/download/v0.9.4/"
             "Optiscaler_0.9.4-final.20260718._MM.7z",),
            archive=True,
        ),
        # OptiScaler 10 nightly: bundled files move to an `OptiScaler/` subfolder; FFX upscaler 4.1.2.4555.
        Asset(
            OPTISCALER_BETA,
            "OptiScaler_v10.0.0-pre1_20261102.7z",
            "7465483deac95ccc93cf05efc9e883e00c03d3186ea79304c076c800bc399501",
            72315137,
            ("https://github.com/optiscaler/OptiScaler-nightly/releases/download/nightly-20261102/"
             "OptiScaler_v10.0.0-pre1_20261102.7z",),
            archive=True,
            generation=10,
        ),
        Asset(
            "reframework-nightly",
            "REFramework.zip",
            "9ef584db4a37715f0a677a5d304a5048b850389875b5dae0e204d4abbe9366f5",
            13269112,
            ("https://github.com/praydog/REFramework-nightly/releases/download/"
             "nightly-01436-1813bf34f720cfed51c0e8f40fc90ed1459a3c6b/REFramework.zip",),
            member="dinput8.dll",
        ),
        Asset(
            "optiscaler-0.10-pre1",
            "OptiScaler.dll",
            "b374b19081cc066365d0c6da4808d768e16469b0cbdfc478b6e95999947d5364",
            25691136,
            (f"{_BLEEDING}/fsr-4-1-1-rdna2/OptiScaler_0.10.0-pre1.20260622_135940.dll",),
        ),
        Asset(
            "fsr-4.0.2c-int8",
            "amd_fidelityfx_upscaler_dx12.dll",
            "c7720bc16bede334f59a1a32cd22edbcbbb159685ed5240e61350a5fb0bc8a94",
            41036800,
            (f"{_BLEEDING}/opti-9-2-a/amd_fidelityfx_upscaler_dx12.dll",),
        ),
        Asset(
            "amdxcffx64-4.1.1",
            "amdxcffx64.dll",
            "a2b136b6affd35a49b141a936be935f7d5ddc8d8f9b8c9afbe62ff9ddb2538a0",
            66830768,
            (f"{_BLEEDING}/fsr-4-1-1/amdxcffx64.dll",),
        ),
        Asset(
            "amdxcffx64-4.1.1-valve",
            "amdxcffx64.dll",
            "4e7dc37aebea3a90e3d3cc43e24cb2b54176b2535315f20dbe63b3b7cfc56b1e",
            65657608,
            (f"{_BLEEDING}/fsr-4-1-1-rdna2/amdxcffx64.dll",),
        ),
        Asset(
            "amdxc64-rdna2",
            "amdxc64.dll",
            "a0a0af61d475e30a70966b3459f3793df772faf8f26ae3261d10554ff592cbd5",
            72656088,
            (f"{_BLEEDING}/fsr-4-1-1-rdna2/amdxc64.dll",),
        ),
    )
}

# FSR4 only runs through the FFX 3.1 path; Dx11 and Vulkan reach it via the D3D12 bridge.
_FSR4_UPSCALERS = {
    "Upscalers.Dx12Upscaler": "fsr31",
    "Upscalers.Dx11Upscaler": "fsr31_12",
    "Upscalers.VulkanUpscaler": "fsr31_12",
}

AMD = ("rdna2", "rdna3", "rdna35", "rdna4")
EVERY_GPU = (*AMD, "intel", "unknown")

BUILDS: dict[str, Build] = {
    build.id: build
    for build in (
        # v10 replaced Fsr4Update/Fsr4ForceEnableInt8 with Fsr4GpuSupport (2 = INT8).
        Build(
            "fsr-4.1.2-beta", "fsr", "4.1.2", ("rdna3", "rdna35"), image=3, cost=2,
            assets=("amdxcffx64-4.1.1",), archive=OPTISCALER_BETA, channel="beta", extra_dir="OptiScaler",
            ini={**_FSR4_UPSCALERS, "FSR.Fsr4GpuSupport": "2"},
        ),
        # Valve's RDNA2 provider pair needs the 0.10 injector, which knows how to load it.
        Build(
            "fsr-4.1.1-rdna2", "fsr", "4.1.1", ("rdna2",), image=3, cost=3,
            assets=("amdxcffx64-4.1.1-valve", "amdxc64-rdna2"),
            injector="optiscaler-0.10-pre1",
            ini={
                **_FSR4_UPSCALERS,
                "FSR.Fsr4Update": "true",
                "FSR.Fsr4ForceModel": "2",
                "Plugins.LoadCustomAmdxc64OnRdna2": "true",
            },
        ),
        Build(
            "fsr-4.1.1", "fsr", "4.1.1", ("rdna3", "rdna35", "rdna4"), image=3, cost=2,
            assets=("amdxcffx64-4.1.1",),
            ini={**_FSR4_UPSCALERS, "FSR.Fsr4Update": "true", "FSR.Fsr4ForceEnableInt8": "true"},
        ),
        Build(
            "fsr-4.0.2c", "fsr", "4.0.2c", ("rdna2", "rdna3", "rdna35"), image=2, cost=3,
            replace={"amd_fidelityfx_upscaler_dx12.dll": "fsr-4.0.2c-int8"},
            ini={**_FSR4_UPSCALERS, "FSR.Fsr4Update": "true"},
        ),
        Build(
            "fsr-3.1", "fsr", "3.1.5", EVERY_GPU, image=1, cost=1,
            ini={"Upscalers.Dx12Upscaler": "fsr31", "FSR.Fsr4Update": "false", "FSR.UpscalerIndex": "1"},
        ),
        Build(
            "xess", "xess", "2", EVERY_GPU, image=2, cost=2,
            ini={"Upscalers.Dx12Upscaler": "xess"},
        ),
    )
}

PREFERRED = {
    "rdna2": "fsr-4.1.1-rdna2",
    "rdna3": "fsr-4.1.1",
    "rdna35": "fsr-4.1.1",
    "rdna4": "fsr-4.1.1",
    "intel": "xess",
}

QUALITY_RATIOS = {"quality": 1.5, "balanced": 1.7, "performance": 2.0, "ultra": 3.0}
EASY_MODES = {"image": "quality", "balanced": "balanced", "fps": "performance"}
SHARPNESS = {"off": None, "soft": 0.3, "high": 0.6}
PROXIES = ("dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "wininet.dll", "winhttp.dll")

# Always set: the log is how Panel proves the upscaler ran, and the HQ font
# auto mode asserts under Proton when its TTF is missing.
BASE_INI = {
    "Log.LogToFile": "true",
    "Log.LogLevel": "2",
    "Menu.UseHQFont": "false",
}


def preferred_build(gpu: str) -> str:
    return PREFERRED.get(gpu, "fsr-3.1")


def build_supported(build: Build, gpu: str) -> bool:
    return gpu in build.gpus


def build_assets(build: Build) -> list[Asset]:
    ids = [build.archive, *build.assets, *build.replace.values()]
    if build.injector:
        ids.append(build.injector)
    return [ASSETS[asset_id] for asset_id in dict.fromkeys(ids)]


def describe(gpu: str) -> list[dict]:
    return [
        {
            "id": build.id,
            "family": build.family,
            "version": build.version,
            "image": build.image,
            "cost": build.cost,
            "available": build.available,
            "channel": build.channel,
            "supported": build_supported(build, gpu),
            "download_bytes": sum(asset.size for asset in build_assets(build)) if build.available else 0,
        }
        for build in BUILDS.values()
    ]


def fg_plan(gpu: str, inputs: dict, recipe_fg: dict | None = None, generation: int = 9) -> dict:
    """Which frame generation path fits this game and GPU: the game's own generator first.

    Recipe paths target the stable build; v10 hooks Streamline 1 DLSSG itself and dropped Nukem's output.
    """
    output = "xefg" if gpu == "intel" else "fsrfg"
    if recipe_fg and generation == 9:
        return {"input": recipe_fg["input"], "output": recipe_fg.get("output", output), "source": "game", "experimental": False}
    if "fsrfg" in inputs:
        return {"input": "fsrfg", "output": output, "source": "game", "experimental": False}
    if "dlssg" in inputs:
        return {"input": "dlssg", "output": output, "source": "game", "experimental": False}
    return {"input": "upscaler", "output": output, "source": "optiscaler", "experimental": True}


def fg_overrides(plan: dict | None, enabled: bool) -> dict[str, str]:
    if not enabled or not plan:
        return {"FrameGen.Enabled": "false", "FrameGen.FGInput": "nofg", "FrameGen.FGOutput": "nofg"}
    overrides = {"FrameGen.Enabled": "true", "FrameGen.FGInput": plan["input"], "FrameGen.FGOutput": plan["output"]}
    if plan["input"] == "upscaler":
        overrides["OptiFG.HUDFix"] = "true"
    return overrides
