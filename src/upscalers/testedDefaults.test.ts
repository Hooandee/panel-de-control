import { describe, expect, it } from "vitest";
import { detectedGameInput, gameUpscalerGuidance, initialBuild, testedDefault } from "./testedDefaults";
import type { BuildInfo, GameDetail, UpscalersOverview } from "./types";

const lite: BuildInfo = { id: "fsr-4.1.2-beta", family: "fsr", version: "4.1.2", available: true, supported: true,
  image: 3, cost: 2, download_bytes: 0, models: ["lite", "full"] };
const dll: BuildInfo = { ...lite, id: "fsr-4.1.2-lite-dll", engine: "dll", models: ["lite"], dll_names: ["amd_fidelityfx_upscaler_dx12.dll"] };
const hardware = { device: "steam_deck_lcd", gpu: "rdna2", builds: [lite, dll], preferred: lite.id, display: [1920, 1080] } as UpscalersOverview;
const detail = { analysis: { target: "/game", inputs: { fsr31: ["amd_fidelityfx_upscaler_dx12.dll"] },
  dll_targets: ["amd_fidelityfx_upscaler_dx12.dll"] }, history: [], install: null } as unknown as GameDetail;

describe("historical profiles", () => {
  it("matches the tested DLL target and prefers it on a fresh install", () => {
    const profile = testedDefault(detail, "3764200", hardware);
    expect(profile).toEqual({ mode: "dll", build: dll.id, model: "lite" });
    expect(initialBuild(lite.id, profile)).toBe(dll.id);
    expect(testedDefault({ ...detail, analysis: { ...detail.analysis, dll_targets: [] } }, "3764200", hardware)).toBeUndefined();
    expect(initialBuild("fsr-4.1.1", profile, true)).toBe("fsr-4.1.1");
  });

  it("marks a resolved Luma route without instructing the player to turn on DLSS", () => {
    const device = { ...hardware, device: "steam_machine", gpu: "rdna3" };
    const solution = { input_reconciled: true, dependencies: ["luma-mrf"], effective_api: "d3d11" } as NonNullable<GameDetail["solution"]>;
    const luma = { ...detail, solutions: { [lite.id]: solution } };
    const guide = gameUpscalerGuidance(luma, "2679460", device.device)!;
    expect(testedDefault(luma, "2679460", device)).toEqual({ mode: "optiscaler", build: lite.id, model: "lite" });
    expect(detectedGameInput(guide, luma, lite)).toBeNull();
    expect(testedDefault(detail, "2679460", device)).toBeUndefined();
    expect(testedDefault(luma, "2679460", device, null, true)).toBeUndefined();
  });

  it("keeps the Lite default when a different model was verified with the user's mod", () => {
    const device = { ...hardware, device: "legion_go_s", gpu: "rdna3" };
    const re4 = { ...detail, solutions: { [lite.id]: { effective_api: "d3d12", dependencies: ["puredark-upscaler-base"] } },
      recipe_info: { user_files: [{ id: "puredark-upscaler-base", state: "ready", version: "1.1.2", installed_version: "1.1.2" }] } } as unknown as GameDetail;
    expect(testedDefault(detail, "2050650", device)).toBeUndefined();
    expect(testedDefault(re4, "2050650", device)).toEqual({ mode: "optiscaler", build: lite.id, model: "full" });
    expect(initialBuild(lite.id, testedDefault(re4, "2050650", device))).toBe(lite.id);
  });

  it("marks spatial Mako only at the tested output on the matching device", () => {
    const device = { ...hardware, device: "rog_ally", gpu: "rdna3" };
    expect(testedDefault(detail, "292030", device, [1920, 1080])).toEqual({ mode: "mako", render: [1280, 720] });
    expect(testedDefault(detail, "292030", device, null)).toBeUndefined();
    expect(testedDefault(detail, "292030", device, [1280, 720])).toBeUndefined();
    expect(testedDefault(detail, "292030", hardware, [1920, 1080])).toBeUndefined();
  });
});

it("ties the historical Fremont fallback to the OptiScaler release that shipped it", () => {
  const older = { ...lite, id: "fsr-4.1.1", version: "4.1.1", models: [] };
  const device = { ...hardware, device: "steam_machine", gpu: "rdna3", builds: [older, lite] };
  const withRelease = (version: string) => ({ ...detail, install: { build: older.id, archive: "optiscaler-0.9.4",
    status: "active", components: [{ id: "optiscaler-0.9.4", version }] } }) as GameDetail;
  expect(testedDefault(detail, "2420110", device)).toBeUndefined();
  expect(testedDefault(withRelease("0.9.4-final"), "2420110", device)).toBeUndefined();
  const previous = testedDefault(withRelease("v0.9.5-final"), "2420110", device);
  expect(previous).toEqual({ mode: "optiscaler", build: older.id, model: null });
  expect(initialBuild(lite.id, previous)).toBe(lite.id);
});
