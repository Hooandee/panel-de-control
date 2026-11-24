"""OptiScaler log verdicts shared with the Windows port.

`shared/fixtures/upscalers/log_verdicts.json` records what `upscalers.logread` reads from each log below: the facts, the
verdict, the FSR 4 provider observation, the FSR 4 fallback and whether ANR FG is generating.
windows/tests/PanelDeControl.Core.Tests/Upscalers must reach the same answers. Times of day and file times depend on the
machine, so `modified` and `started` are left out. Rewrite it after a change with
`PYTHONPATH=py_modules python tests/test_upscalers_log_parity.py --write`.
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "logread", Path(__file__).parents[1] / "py_modules" / "upscalers" / "logread.py")
logread = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("logread", logread)
_SPEC.loader.exec_module(logread)

FIXTURE = Path(__file__).parents[1] / "shared" / "fixtures" / "upscalers" / "log_verdicts.json"
LOGS = Path(__file__).parent / "fixtures" / "upscalers"
MTIME = 1_700_000_000
VOLATILE = ("modified", "started")
FSR4 = "fsr-4.1.2-beta"

VULKAN_FALLBACK = (LOGS / "vulkan_fsr4_fallback.log").read_text()
D3D11_EXPOSURE = (LOGS / "d3d11_exposure_fallback.log").read_text()
FSR4_PROVIDER = (LOGS / "fsr4_lite_provider_gow_rdna2.log").read_text()
LOADED_ONLY = ("[13:19:00.245658] [W] OptiScaler v0.9.4-final (7534ad0) loaded\n"
               "[13:19:00.252768] [I] CheckWorkingMode OptiScaler working as dxgi.dll, system dll loaded\n"
               "[13:19:07.990345] [E] hkD3D12CreateDevice ppDevice is nullptr\n")
FSR31 = (LOADED_ONLY +
         "[13:21:05.132712] [I] CreateDLSSContext renderWidth: 936, maxWidth: 1440, ratio: 1.5384616\n"
         "[13:21:05.132848] [I] NVSDK_NGX_D3D12_CreateFeature Creating new fsr31 upscaler\n"
         "[13:21:05.132956] [I] IFeature::SetInitParameters Render Resolution: 936x624, Display Resolution 1440x960, Quality: 1\n")
D3D11_BRIDGE = (
    "[13:20:25.453743] [I] NVSDK_NGX_D3D11_CreateFeature Creating new FSR 3.X w/Dx12 feature\n"
    "[13:20:25.453838] [I] IFeature::SetInitParameters Render Resolution: 752x423, Display Resolution 1280x720, Quality: 3\n"
    "[13:20:26.217677] [I] WithDx12::GetD3D12DeviceFromD3D11 D3D12 interop device created on D3D11 adapter: AMD Custom GPU\n")
OPTISCALER10 = ("[00:05:24.702753] [W] OptiScaler v10.0.0-dev (ab379b25) (20261102_120120) loaded\n"
                "[00:06:04.046244] [I] TryCreateOptiFeature Creating FSR 3.X upscaler feature\n"
                "[00:06:04.046456] [I] IFeature::SetInitParameters Render Resolution: 936x624, Display Resolution 1440x960, Quality: 1\n")
FSR4_RUNNING = ("[I] NVSDK_NGX_VULKAN_CreateFeature1 Creating new FSR 3.X/4 w/Dx12 upscaler\n"
                "[I] FeatureProvider_Vk::ChangeFeature init successful for FSR 4.1.2 Lite, upscaler changed\n")
OPTIFG = "[I] FrameGen.FGInput: {}\n[I] FSRFG_Dx12::CreateContext D3D12_CreateContext result: 0\n"
ANR_START = "[16:38:04.831] [info] frame generation feature: 3840x2160\n"
ANR_PACING = ("[16:40:57.540] [info] pacing: 274 real frames in 10.0 s, interval median 36.45 ms; "
              "evaluates ours 274 NVIDIA's 0; our evaluate CPU p99 0.390\n")
ANR_IDLE = ANR_PACING.replace("evaluates ours 274", "evaluates ours 0")


def _case(name, log, **extra):
    return {"name": name, "log": log, **extra}


CASES = [
    _case("no-log", None),
    _case("stale-log-is-not-run", FSR31, since=MTIME + 100),
    _case("log-newer-than-install", FSR31, since=MTIME - 100),
    _case("empty-log", ""),
    _case("loaded-only", LOADED_ONLY),
    _case("active-fsr31", FSR31),
    _case("active-fsr31-install-asks-fsr3", FSR31, requested="fsr-3.1"),
    _case("optiscaler-10-fsr-3x", OPTISCALER10),
    _case("fsr-input-is-not-dlss", "[I] ffxCreateContext_Dx12 context created: 1EE8\n"
          "[I] CreateDLSSContext renderWidth: 936, maxWidth: 1440, ratio: 1.5384616\n"
          "[I] FSRFG_Dx12::Activate D3D12_Configure Enabled: true, result: FFX_API_RETURN_OK (0)\n"),
    _case("latest-input-wins-xess", "ffxCreateContext_Dx12 context created: 1EE8\nCreateDLSSContext renderWidth: 960\nhk_xessD3D11Execute\n"),
    _case("latest-input-wins-fsr3", "hk_xessD3D11Execute\nffxCreateContext_Dx12 context created: 1EE8\nCreateDLSSContext renderWidth: 960\n"),
    _case("latest-input-wins-fsr2", "ffxCreateContext_Dx12 context created: 1EE8\nffxFsr2ContextCreate_Dx11 context created: 42\n"),
    _case("xess-vulkan-input", "hk_xessVKExecute\nCreateDLSSContext\n"),
    _case("unattributed-dlss-context", "[D] CreateDLSSContext\n"),
    _case("d3d12-backend-names-no-input", "[I] NVSDK_NGX_D3D12_CreateFeature Creating new fsr31 upscaler\nCreateDLSSContext\n"),
    _case("d3d11-init-only-is-loaded", "[I] NVSDK_NGX_D3D11_Init_Ext AppId: 100980011\n"),
    _case("d3d11-bridged-to-d3d12", D3D11_BRIDGE),
    _case("d3d11-exposure-fallback", D3D11_EXPOSURE),
    _case("fsr4-provider-with-fsr3x-entry", FSR4_PROVIDER + "[I] Creating new FSR 3.X upscaler\n", requested=FSR4),
    _case("fsr4-provider-queried-but-not-run", FSR4_PROVIDER, requested=FSR4),
    _case("fsr4-provider-then-xess", FSR4_PROVIDER + "[I] init successful for XeSS, upscaler changed\n"),
    _case("fsr4-provider-older-fsr31", FSR4_PROVIDER + "[I] Creating new FSR 3.1 upscaler\n", requested=FSR4),
    _case("fsr4-provider-texture-failure", FSR4_PROVIDER +
          "[I] Creating new FSR 3.X upscaler\n[E] Can't process Vulkan textures!\n", requested=FSR4),
    _case("fsr4-provider-other-effect-ignored", FSR4_PROVIDER +
          "[I] FSR4DriverDll::QueryProvider amdxcffx64.dll provider for 20000: 4.0.9 *, id: 1, struct version: 2\n"
          "[I] Creating new FSR 3.X upscaler\n"),
    _case("fsr4-model-int8", "[I] Upscaler support - fsr4: int8, dlss: false\n"
          "[I] FSR4DriverDll::QueryProvider amdxcffx64.dll provider for 10000: 4.0.2 *, id: 1\n[I] Creating new fsr31 upscaler\n"),
    _case("fsr4-model-fp8", "[I] Upscaler support - fsr4: fp8, dlss: false\n"
          "[I] FSR4DriverDll::QueryProvider amdxcffx64.dll provider for 10000: 4.1.0 *, id: 1\n[I] Creating new FSR 3.X/4 upscaler\n"),
    _case("fsr4-running-no-fallback", FSR4_RUNNING, requested=FSR4),
    _case("fsr4-entry-fsr31-no-fallback", "[I] Creating new fsr31 upscaler\n[I] amdxcffx64.dll loaded\n", requested="fsr-4.1.1"),
    _case("vulkan-fsr4-fallback", VULKAN_FALLBACK, requested=FSR4),
    _case("vulkan-fallback-fsr3-install-asks-nothing", VULKAN_FALLBACK, requested="fsr-3.1"),
    _case("vulkan-fallback-xess-install-asks-nothing", VULKAN_FALLBACK, requested="xess"),
    _case("fsr2-without-fsr4-request", "[I] init successful for FSR 2.2.1, upscaler changed\n", requested="fsr-3.1"),
    _case("failed-once-then-fsr4-runs", VULKAN_FALLBACK + FSR4_RUNNING.replace("FSR 4.1.2 Lite", "FSR 4.1.2"), requested=FSR4),
    _case("texture-failure-alone", "[I] Creating new FSR 3.X/4 w/Dx12 upscaler\n"
          "[E] IFeature_VkwDx12::Evaluate Can't process Vulkan textures!\n", requested=FSR4),
    _case("numbered-fsr3-is-backend-changed", "[I] init successful for FSR 3.1.4, upscaler changed\n", requested="fsr-4.0.2c"),
    _case("fsr4-requested-no-log-evidence", LOADED_ONLY, requested=FSR4),
    _case("fsr4-requested-stale-log", VULKAN_FALLBACK, requested=FSR4, since=MTIME + 1),
    _case("optifg-context-from-upscaler-input", OPTIFG.format("upscaler")),
    _case("optifg-context-from-game-input", OPTIFG.format("fsrfg")),
    _case("fg-last-toggle-wins", OPTIFG.format("upscaler") +
          "[I] FSRFG_Dx12::Deactivate D3D12_Configure Enabled: false, result: FFX_API_RETURN_OK (0)\n"),
    _case("fg-enabled-then-set-enabled-false", "[I] FSRFG_Dx12::Activate D3D12_Configure Enabled: true, result: 0\n"
          "[I] FGFeature::SetEnabled: false, result: SUCCESS\n"),
    _case("fg-set-enabled-success", "[I] FGFeature::SetEnabled: true, result: FFX_API_RETURN_OK_SUCCESS\n"),
    _case("fg-nukem-bridge", "[I] Nukem's bridge initialized\n"),
    _case("xefg-not-redirected", "[W] XeFGInputs::Redirect OptiScaler's library is missing exports of the game's, not redirecting\n"
          "[I] XeFGInputs::Hook XeFG passthrough: false\n"),
    _case("xefg-context", "[I] FrameGen.FGInput: upscaler\n[I] XeFG context created\n"),
    _case("gpu-and-proxy", "[I] CheckWorkingMode OptiScaler working as version.dll, system dll loaded\n"
          "[I] [serial] Adapter Desc: AMD VANGOGH\n"),
    _case("errors-grouped-by-source", "[E] hkD3D12CreateDevice ppDevice is nullptr\n[E] hkD3D12CreateDevice ppDevice is nullptr\n"
          "[C] `anonymous-namespace'::PrepareCachedResource Exposure missing\n[E] \n[E]    Foo::Bar failed\n[W] not an error\n"
          + "".join(f"[E] Source{n}::Fail\n" * n for n in range(1, 9))),
    _case("crlf-line-endings", "[I] Creating new fsr31 upscaler\r\n[E] Foo::Bar failed\r\n"),
    _case("anr-not-written-yet", None, anr_log=None),
    _case("anr-no-summary-yet", None, anr_log=ANR_START),
    _case("anr-generating", None, anr_log=ANR_START + ANR_PACING, anr_now_after=5),
    _case("anr-summary-stale", None, anr_log=ANR_START + ANR_PACING, anr_now_after=logread.ANR_FRESH_S + 1),
    _case("anr-later-line-after-end", None, anr_log=ANR_START + ANR_PACING +
          "[16:41:40.000] [info] pacing spike: real frame interval 353.63 ms\n", anr_now_after=5),
    _case("anr-evaluating-zero-frames", None, anr_log=ANR_START + ANR_IDLE, anr_now_after=5),
    _case("anr-newest-summary-wins", None, anr_log=ANR_START + ANR_PACING + ANR_IDLE.replace("16:40:57", "16:41:07"), anr_now_after=5),
    _case("anr-clock-wraps-midnight", None, anr_log=ANR_PACING.replace("16:40:57", "23:59:55") +
          "[00:00:10.000] [info] frame generation feature: 3840x2160\n", anr_now_after=5),
]


def _expected(case: dict) -> dict:
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        if case["log"] is not None:
            log = folder / logread.LOG_NAME
            log.write_bytes(case["log"].encode("utf-8"))
            os.utime(log, (MTIME, MTIME))
        facts = logread.read(folder, case.get("since"))
        install = {"engine": "optiscaler", "build": case["requested"]} if case.get("requested") else None
        anr = None
        if "anr_log" in case:
            anr_folder = folder / "dlssg"
            if case["anr_log"] is not None:
                anr_folder.mkdir()
                nr_fg = anr_folder / "nr_fg-1.log"
                nr_fg.write_bytes(case["anr_log"].encode("utf-8"))
                os.utime(nr_fg, (MTIME, MTIME))
            anr = logread.anr_generating(anr_folder, MTIME + case.get("anr_now_after", 0))
    return {
        "facts": {key: value for key, value in facts.items() if key not in VOLATILE},
        "verdict": logread.verdict(facts),
        "provider_observation": logread.provider_observation(facts),
        "fallback": logread.fallback(install, facts) if install else None,
        "anr_generating": anr,
    }


def snapshot() -> dict:
    return json.loads(json.dumps({
        "schema_version": 1,
        "mtime": MTIME,
        "cases": [{**case, "expected": _expected(case)} for case in CASES],
    }))


def test_fixture_matches_the_linux_backend():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == snapshot()


def test_cases_cover_every_verdict_and_provider_confidence():
    expected = [case["expected"] for case in snapshot()["cases"]]
    assert {item["verdict"] for item in expected} == {"not_run", "loaded", "active"}
    assert {item["provider_observation"]["provider_confidence"] for item in expected} == {"unknown", "family_only", "log_provider"}
    assert {item["provider_observation"]["provider_model"] for item in expected} >= {"Lite", "INT8", "FP8", None}
    assert {item["anr_generating"] for item in expected} == {None, True, False}
    assert {item["fallback"]["reason"] for item in expected if item["fallback"]} == {"vulkan_textures", "backend_changed"}


if __name__ == "__main__" and "--write" in sys.argv:
    FIXTURE.write_text(json.dumps(snapshot(), separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
