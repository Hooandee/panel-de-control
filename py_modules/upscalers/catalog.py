"""Upscaler builds Panel can install, identified by content hash.

A build is the user's "version" choice. Every file it needs is an asset whose
identity is its SHA-256; URLs are interchangeable mirrors, so moving a download
never invalidates an install.
"""

from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath

OPTISCALER_ARCHIVE = "optiscaler-0.9.4"
OPTISCALER_BETA = "optiscaler-10-nightly"
LSFG_ARCHIVE = "lsfg-vk-2.0.0"
HELIXSR_ARCHIVE = "helixsr-3.2.0"
OPTIPATCHER = "optipatcher-0.42"


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


_BLEEDING = "https://github.com/xXJSONDeruloXx/OptiScaler-Bleeding-Edge/releases/download"

ASSETS: dict[str, Asset] = {
    asset.id: asset
    for asset in (
        Asset(
            LSFG_ARCHIVE, "lsfg-vk-2.0.0.tar.xz",
            "08bdbdf373a111022df87dac7aa87e3b564bb841f961552e3ca85fea12b5aa74", 561348,
            ("https://builds.lsfg-vk.dev/lsfg-vk-2.0.0.tar.xz",), archive=True,
        ),
        # Official release, unmodified (HelixSR Freeware License). Only HLX FSR 4 (prebuilt, from AMD's MIT
        # FSR SDK) is offered: HLX DLSS needs NVIDIA's DLSS DLL taken apart for AMD, which NVIDIA's licence forbids.
        Asset(
            HELIXSR_ARCHIVE, "HelixSR-3.2.0.zip",
            "a4e83da8b4335a886197aef10e8f8a8947a2e32e5e1eebfdf060ff00724c17c7", 217396302,
            ("https://github.com/lonewolf0622/HelixSR/releases/download/v3.2.0/HelixSR-3.2.0.zip",),
        ),
        # MIT; lets supported games offer DLSS/DLSS-FG to OptiScaler without spoofing (OptiScaler loads *.asi from plugins).
        Asset(
            OPTIPATCHER, "OptiPatcher.asi",
            "2a6e033aeda72d63281889480b2380da830530cf6e1e448e2056d451ade75f1b", 107520,
            ("https://github.com/optiscaler/OptiPatcher/releases/download/v0.42/OptiPatcher_v0.42.asi",),
        ),
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
            "fsr-4.1.2-dll-loader", "FSR4_FP8_4.1.2.4555.7z",
            "7b6300ccf19f91ce27b2729f53aa1e4a907e6ea46ae9e93d313a206e2aee68ff", 18256621,
            ("https://github.com/Optiscaler-Client/Optiscaler-Extras-FP8/releases/download/FSR_4.1.2.4555/FSR4_FP8_4.1.2.4555.7z",),
            member="amd_fidelityfx_loader_dx12.dll",
        ),
        Asset(
            "fsr-4.1.2-dll-upscaler", "FSR4_FP8_4.1.2.4555.7z",
            "7b6300ccf19f91ce27b2729f53aa1e4a907e6ea46ae9e93d313a206e2aee68ff", 18256621,
            ("https://github.com/Optiscaler-Client/Optiscaler-Extras-FP8/releases/download/FSR_4.1.2.4555/FSR4_FP8_4.1.2.4555.7z",),
            member="amd_fidelityfx_upscaler_dx12.dll",
        ),
        Asset(
            "fsr-4.1.2-dll-framegeneration", "FSR4_FP8_4.1.2.4555.7z",
            "7b6300ccf19f91ce27b2729f53aa1e4a907e6ea46ae9e93d313a206e2aee68ff", 18256621,
            ("https://github.com/Optiscaler-Client/Optiscaler-Extras-FP8/releases/download/FSR_4.1.2.4555/FSR4_FP8_4.1.2.4555.7z",),
            member="amd_fidelityfx_framegeneration_dx12.dll",
        ),
        Asset(
            "fsr-4.1.1-dll-loader", "FSR4_FP8_4.1.1.2740.7z",
            "e722e39893d4470e11e3993d8240cbec47c5ae3398fb7dfdc387ec8b0038698d", 17068121,
            ("https://github.com/Optiscaler-Client/Optiscaler-Extras-FP8/releases/download/FSR_4.1.1.2740/FSR4_FP8_4.1.1.2740.7z",),
            member="amd_fidelityfx_loader_dx12.dll",
        ),
        Asset(
            "fsr-4.1.1-dll-upscaler", "FSR4_FP8_4.1.1.2740.7z",
            "e722e39893d4470e11e3993d8240cbec47c5ae3398fb7dfdc387ec8b0038698d", 17068121,
            ("https://github.com/Optiscaler-Client/Optiscaler-Extras-FP8/releases/download/FSR_4.1.1.2740/FSR4_FP8_4.1.1.2740.7z",),
            member="amd_fidelityfx_upscaler_dx12.dll",
        ),
        Asset(
            "fsr-4.1.1-dll-framegeneration", "FSR4_FP8_4.1.1.2740.7z",
            "e722e39893d4470e11e3993d8240cbec47c5ae3398fb7dfdc387ec8b0038698d", 17068121,
            ("https://github.com/Optiscaler-Client/Optiscaler-Extras-FP8/releases/download/FSR_4.1.1.2740/FSR4_FP8_4.1.1.2740.7z",),
            member="amd_fidelityfx_framegeneration_dx12.dll",
        ),
        Asset(
            "fsr-4.1.2-lite-cyboman-dll", "fsr4.1.2-igpu-cyboman-rdna2-2026-11-05.7z",
            "da7c7681bffe7ac60a01e859d5b107900d963557793ef67ddcfd03a832e1c03f", 9567439,
            ("https://github.com/zgauthier2000/fsr4-shader-performance-overrides/releases/download/dll-2026-11-05/fsr4.1.2-igpu-cyboman-rdna2-2026-11-05.7z",),
            member="4.1.2l-exact/amd_fidelityfx_upscaler_dx12.dll",
        ),
        Asset(
            "fsr-4.1.2-lite-igpu-cyboman-dll", "fsr4.1.2-igpu-cyboman-rdna3-2026-11-05.7z",
            "6553cfeaa824fd1fa36985278e5ce835d27bbb758e99a1db5efaf331fe72dc4f", 9553046,
            ("https://github.com/zgauthier2000/fsr4-shader-performance-overrides/releases/download/dll-2026-11-05/fsr4.1.2-igpu-cyboman-rdna3-2026-11-05.7z",),
            member="4.1.2l-exact/amd_fidelityfx_upscaler_dx12.dll",
        ),
        Asset(
            "fsr-4.1.1-lite-exact-dll", "FSR4_INT8_4.1.1_Lite_Exact.zip",
            "dac25f79687f955d7651451c24e9a827e1989e61389565befce267b0b2fef68e", 22379952,
            ("https://github.com/Optiscaler-Client/Optiscaler-Extras/releases/download/FSR_4.1.1_Lite_Exact/FSR4_INT8_4.1.1_Lite_Exact.zip",),
            member="amd_fidelityfx_upscaler_dx12.dll",
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
        Build(
            "fsr-4.1.2-dll", "fsr", "4.1.2", AMD, image=3, cost=2, engine="dll", way="fsr",
            replace={f"amd_fidelityfx_{part}_dx12.dll": f"fsr-4.1.2-dll-{part}" for part in ("loader", "upscaler", "framegeneration")},
        ),
        Build(
            "fsr-4.1.2-lite-dll", "fsr", "4.1.2", ("rdna2",), image=3, cost=2, engine="dll", way="fsr",
            replace={"amd_fidelityfx_upscaler_dx12.dll": "fsr-4.1.2-lite-cyboman-dll"}, models=(("lite", {}),),
            legacy_replace={f"amd_fidelityfx_{part}_dx12.dll": f"fsr-4.1.2-dll-{part}" for part in ("loader", "framegeneration")},
        ),
        Build(
            "fsr-4.1.2-lite-igpu-dll", "fsr", "4.1.2", ("rdna3",), image=3, cost=2, engine="dll", way="fsr",
            replace={"amd_fidelityfx_upscaler_dx12.dll": "fsr-4.1.2-lite-igpu-cyboman-dll"}, models=(("lite", {}),),
            legacy_replace={f"amd_fidelityfx_{part}_dx12.dll": f"fsr-4.1.2-dll-{part}" for part in ("loader", "framegeneration")},
        ),
        Build(
            "fsr-4.1.1-dll", "fsr", "4.1.1", ("rdna3", "rdna35", "rdna4"), image=3, cost=2, engine="dll", way="fsr",
            replace={f"amd_fidelityfx_{part}_dx12.dll": f"fsr-4.1.1-dll-{part}" for part in ("loader", "upscaler", "framegeneration")},
        ),
        Build(
            "fsr-4.1.1-lite-dll", "fsr", "4.1.1", ("rdna2", "rdna3", "rdna35"), image=3, cost=2, engine="dll", way="fsr",
            replace={"amd_fidelityfx_upscaler_dx12.dll": "fsr-4.1.1-lite-exact-dll"}, models=(("lite", {}),),
            legacy_replace={f"amd_fidelityfx_{part}_dx12.dll": f"fsr-4.1.2-dll-{part}" for part in ("loader", "framegeneration")},
        ),
        Build(
            "fsr-4.0.2c-dll", "fsr", "4.0.2c", ("rdna2", "rdna3", "rdna35"), image=2, cost=3, engine="dll", way="fsr",
            replace={"amd_fidelityfx_upscaler_dx12.dll": "fsr-4.0.2c-int8"},
            legacy_replace={f"amd_fidelityfx_{part}_dx12.dll": f"fsr-4.1.2-dll-{part}" for part in ("loader", "framegeneration")},
        ),
        # v10 replaced Fsr4Update/Fsr4ForceEnableInt8 with Fsr4GpuSupport (2 = INT8, 4 = INT8Lite).
        # Lite is the default, as AMD's driver picks for APUs; full INT8 stays one tap away.
        Build(
            "fsr-4.1.2-beta", "fsr", "4.1.2", ("rdna2", "rdna3", "rdna35"), image=3, cost=2,
            assets=("amdxcffx64-4.1.1",), archive=OPTISCALER_BETA, channel="beta", extra_dir="OptiScaler",
            ini={**_FSR4_UPSCALERS, "FSR.Fsr4GpuSupport": "4"},
            models=(("lite", {"FSR.Fsr4GpuSupport": "4"}), ("full", {"FSR.Fsr4GpuSupport": "2"})),
        ),
        # Valve's RDNA2 provider pair uses the v10 driver-provider path.
        Build(
            "fsr-4.1.1-rdna2", "fsr", "4.1.1", ("rdna2",), image=3, cost=3,
            assets=("amdxcffx64-4.1.1-valve", "amdxc64-rdna2"),
            archive=OPTISCALER_BETA, extra_dir="OptiScaler",
            ini={
                "Upscalers.Dx12Upscaler": "ffx",
                "Upscalers.Dx11Upscaler": "ffx_12",
                "Upscalers.VulkanUpscaler": "ffx_12",
                "FSR.Fsr4GpuSupport": "2",
                "FSR.UpscalerIndex": "1",
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
            ini={"Upscalers.Dx12Upscaler": "fsr31", "Upscalers.Dx11Upscaler": "fsr31",
                 "Upscalers.VulkanUpscaler": "fsr31", "FSR.Fsr4Update": "false", "FSR.UpscalerIndex": "0"},
        ),
        Build(
            "xess", "xess", "2", EVERY_GPU, image=2, cost=2,
            # Native XeSS on DX11 only runs on Arc; elsewhere it goes through the D3D12 bridge.
            ini={"Upscalers.Dx12Upscaler": "xess", "Upscalers.Dx11Upscaler": "xess_12", "Upscalers.VulkanUpscaler": "xess"},
        ),
        # Proton-GE/EM and official Proton swap FSR 3.1 for FSR 4 themselves; the GPU and the game's Proton decide.
        Build("proton-fsr4", "proton", "FSR 4", ("rdna3", "rdna4"), image=3, cost=2, engine="proton"),
        Build(
            "hlx-fsr4", "helixsr", "FSR 4", (*AMD, "intel"), image=3, cost=2,
            archive=HELIXSR_ARCHIVE, channel="beta", engine="helixsr", way="fsr",
        ),
    )
}

PREFERRED = {
    # OptiScaler 10 runs FSR 4.1.2 Lite on Van Gogh, as AMD's driver picks for APUs.
    "rdna2": "fsr-4.1.2-beta",
    "rdna3": "fsr-4.1.1",
    "rdna35": "fsr-4.1.1",
    "rdna4": "fsr-4.1.1",
    "intel": "xess",
}

QUALITY_RATIOS = {"native": 1.0, "quality": 1.5, "balanced": 1.7, "performance": 2.0, "ultra": 3.0}
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


FFX_LOADER = "amd_fidelityfx_loader_dx12.dll"


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
