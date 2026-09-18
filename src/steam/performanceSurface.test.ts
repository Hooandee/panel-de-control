import { describe, expect, it } from "vitest";

import {
  composeSteamPerformanceRows,
  performanceLayoutFromStore,
  selectSteamPerformanceComponents,
} from "./performanceSurface";

const component = (...tokens: string[]) => {
  const candidate = () => null;
  Object.defineProperty(candidate, "toString", {
    value: () => tokens.join(" "),
  });
  return candidate;
};

const exportsFixture = () => ({
  profile: component("#QuickAccess_Tab_Perf_ToggleGameSettings", "GameProfileExplainer"),
  legacyFrameRate: component("#QuickAccess_Tab_Perf_LimitFrameRate", "LimitFramerateSlider"),
  appFrameRate: component("#QuickAccess_Tab_Perf_AppRefreshRate", "gamescope_app_target_framerate"),
  disableFrameLimit: component("#QuickAccess_Tab_Perf_DisableFrameLimit", "gamescope_disable_framelimit"),
  refreshRate: component("#QuickAccess_Tab_Perf_RefreshRate", "onChangeComplete"),
  variableResolution: component("#QuickAccess_Tab_Perf_VariableResolution", "SetVariableResolutionEnabled"),
  combinedScaling: component("#QuickAccess_Tab_Perf_ScalingFilter_Integer", "#QuickAccess_Tab_Perf_ScalingFilter_NIS"),
  splitScalingFilter: component("#QuickAccess_Tab_Perf_ScalingFilter", "notchTicksVisible"),
  scalingMode: component("#QuickAccess_Tab_Perf_ScalingScaler", "notchTicksVisible"),
  fsrSharpness: component("#QuickAccess_Tab_Perf_FSRSharpness", "#QuickAccess_Tab_Perf_ScalingFilter_FSRSharpness_Explainer"),
  nisSharpness: component("#QuickAccess_Tab_Perf_NISSharpness", "#QuickAccess_Tab_Perf_ScalingFilter_NISSharpness_Explainer"),
  allowTearing: component("#QuickAccess_Tab_Perf_EnableTearing", "gamescope_allow_tearing"),
  vrr: component("#QuickAccess_Tab_Perf_EnableVRR", "#QuickAccess_Tab_Perf_VRR_NotCapable"),
  reset: component("#QuickAccess_Tab_Perf_ResetToDefault", "ResetCurrentPerfProfileSettings"),
});

describe("Steam performance component discovery", () => {
  it("resolves every approved native control by a two-token signature", () => {
    const selected = selectSteamPerformanceComponents(exportsFixture());

    expect(Object.keys(selected)).toEqual([
      "profile",
      "legacyFrameRate",
      "appFrameRate",
      "disableFrameLimit",
      "refreshRate",
      "variableResolution",
      "combinedScaling",
      "splitScalingFilter",
      "scalingMode",
      "fsrSharpness",
      "nisSharpness",
      "allowTearing",
      "vrr",
      "reset",
    ]);
  });

  it("fails closed for an ambiguous export instead of choosing a second writer", () => {
    const fixture = exportsFixture();
    const selected = selectSteamPerformanceComponents({
      ...fixture,
      duplicateTearing: component(
        "#QuickAccess_Tab_Perf_EnableTearing",
        "gamescope_allow_tearing",
      ),
    });

    expect(selected.allowTearing).toBeUndefined();
    expect(selected.vrr).toBe(fixture.vrr);
  });

  it("omits a function that collides across two control signatures", () => {
    const fixture = exportsFixture();
    const withoutScaling = Object.fromEntries(
      Object.entries(fixture).filter(([id]) => (
        id !== "combinedScaling" && id !== "splitScalingFilter"
      )),
    );
    const scalingCollision = component(
      "#QuickAccess_Tab_Perf_ScalingFilter_Integer",
      "#QuickAccess_Tab_Perf_ScalingFilter_NIS",
      "#QuickAccess_Tab_Perf_ScalingFilter",
      "notchTicksVisible",
    );
    const selected = selectSteamPerformanceComponents({
      ...withoutScaling,
      scalingCollision,
    });

    expect(selected.combinedScaling).toBeUndefined();
    expect(selected.splitScalingFilter).toBeUndefined();
    expect(selected.vrr).toBe(fixture.vrr);
  });

  it("recognizes current Steam variable-resolution and sharpness controls", () => {
    const variableResolution = component(
      "#QuickAccess_Tab_Perf_VariableResolution",
      "#QuickAccess_Tab_Perf_VariableResolution_Explainer",
    );
    const sharpness = component(
      "#QuickAccess_Tab_Perf_Sharpness",
      "#QuickAccess_Tab_Perf_ScalingFilter_Sharpness_Explainer",
    );

    expect(selectSteamPerformanceComponents({ variableResolution, sharpness })).toEqual({
      variableResolution,
      sharpness,
    });
  });
});

describe("Steam performance route composition", () => {
  it("uses the legacy FPS and combined-scaling writers only on the legacy route", () => {
    const components = selectSteamPerformanceComponents(exportsFixture());
    const rows = composeSteamPerformanceRows(components, {
      frameRate: "legacy",
      splitScaling: false,
    });

    expect(rows.map((row) => row.id)).toEqual([
      "profile",
      "legacyFrameRate",
      "refreshRate",
      "variableResolution",
      "vrr",
      "allowTearing",
      "combinedScaling",
      "fsrSharpness",
      "nisSharpness",
      "reset",
    ]);
  });

  it("uses the app-target FPS and split-scaling writers only on the modern route", () => {
    const components = selectSteamPerformanceComponents(exportsFixture());
    const rows = composeSteamPerformanceRows(components, {
      frameRate: "app_target",
      splitScaling: true,
    });

    expect(rows.map((row) => row.id)).toEqual([
      "profile",
      "appFrameRate",
      "disableFrameLimit",
      "variableResolution",
      "vrr",
      "allowTearing",
      "scalingMode",
      "splitScalingFilter",
      "fsrSharpness",
      "nisSharpness",
      "reset",
    ]);
  });

  it("infers the current split-scaling route when Steam omits the legacy capability flag", () => {
    const scalingMode = component(
      "#QuickAccess_Tab_Perf_ScalingScaler",
      "notchTicksVisible",
    );
    const splitScalingFilter = component(
      "#QuickAccess_Tab_Perf_ScalingFilter",
      "notchTicksVisible",
    );
    const sharpness = component(
      "#QuickAccess_Tab_Perf_Sharpness",
      "#QuickAccess_Tab_Perf_ScalingFilter_Sharpness_Explainer",
    );
    const components = selectSteamPerformanceComponents({
      scalingMode,
      splitScalingFilter,
      sharpness,
    });

    expect(composeSteamPerformanceRows(components, {
      frameRate: "app_target",
      splitScaling: null,
    }).map((row) => row.id)).toEqual([
      "scalingMode",
      "splitScalingFilter",
      "sharpness",
    ]);
  });

  it("omits scaling when Steam publishes both routes without a capability flag", () => {
    const components = selectSteamPerformanceComponents(exportsFixture());
    const ids = composeSteamPerformanceRows(components, {
      frameRate: "legacy",
      splitScaling: null,
    }).map((row) => row.id);

    expect(ids).not.toContain("combinedScaling");
    expect(ids).not.toContain("scalingMode");
  });

  it("derives the active routes only from Steam's published limits", () => {
    expect(performanceLayoutFromStore({
      msgLimits: {
        disable_refresh_rate_management: true,
        is_split_scaling_and_filtering_supported: true,
      },
    })).toEqual({ frameRate: "app_target", splitScaling: true });

    expect(performanceLayoutFromStore({ msgLimits: {} })).toEqual({
      frameRate: "legacy",
      splitScaling: null,
    });
    expect(performanceLayoutFromStore({})).toBeNull();
  });
});
