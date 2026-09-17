import type { ComponentType } from "react";

export type SteamPerformanceComponent = ComponentType<Record<string, unknown>>;

export interface SteamPerformanceComponents {
  profile?: SteamPerformanceComponent;
  legacyFrameRate?: SteamPerformanceComponent;
  appFrameRate?: SteamPerformanceComponent;
  disableFrameLimit?: SteamPerformanceComponent;
  refreshRate?: SteamPerformanceComponent;
  variableResolution?: SteamPerformanceComponent;
  combinedScaling?: SteamPerformanceComponent;
  splitScalingFilter?: SteamPerformanceComponent;
  scalingMode?: SteamPerformanceComponent;
  fsrSharpness?: SteamPerformanceComponent;
  nisSharpness?: SteamPerformanceComponent;
  allowTearing?: SteamPerformanceComponent;
  vrr?: SteamPerformanceComponent;
  reset?: SteamPerformanceComponent;
}

export type SteamPerformanceComponentId = keyof SteamPerformanceComponents;

export interface SteamPerformanceLayout {
  frameRate: "legacy" | "app_target";
  splitScaling: boolean;
}

export interface SteamPerformanceStoreView {
  msgLimits?: {
    disable_refresh_rate_management?: unknown;
    is_split_scaling_and_filtering_supported?: unknown;
  };
}

export interface SteamPerformanceRow {
  id: SteamPerformanceComponentId;
  Component: SteamPerformanceComponent;
}

const SIGNATURES: Record<SteamPerformanceComponentId, readonly string[]> = {
  profile: ["#QuickAccess_Tab_Perf_ToggleGameSettings", "GameProfileExplainer"],
  legacyFrameRate: ["#QuickAccess_Tab_Perf_LimitFrameRate", "LimitFramerateSlider"],
  appFrameRate: ["#QuickAccess_Tab_Perf_AppRefreshRate", "gamescope_app_target_framerate"],
  disableFrameLimit: ["#QuickAccess_Tab_Perf_DisableFrameLimit", "gamescope_disable_framelimit"],
  refreshRate: ["#QuickAccess_Tab_Perf_RefreshRate", "onChangeComplete"],
  variableResolution: ["#QuickAccess_Tab_Perf_VariableResolution", "SetVariableResolutionEnabled"],
  combinedScaling: ["#QuickAccess_Tab_Perf_ScalingFilter_Integer", "#QuickAccess_Tab_Perf_ScalingFilter_NIS"],
  splitScalingFilter: ["#QuickAccess_Tab_Perf_ScalingFilter", "notchTicksVisible"],
  scalingMode: ["#QuickAccess_Tab_Perf_ScalingScaler", "notchTicksVisible"],
  fsrSharpness: ["#QuickAccess_Tab_Perf_FSRSharpness", "#QuickAccess_Tab_Perf_ScalingFilter_FSRSharpness_Explainer"],
  nisSharpness: ["#QuickAccess_Tab_Perf_NISSharpness", "#QuickAccess_Tab_Perf_ScalingFilter_NISSharpness_Explainer"],
  allowTearing: ["#QuickAccess_Tab_Perf_EnableTearing", "gamescope_allow_tearing"],
  vrr: ["#QuickAccess_Tab_Perf_EnableVRR", "#QuickAccess_Tab_Perf_VRR_NotCapable"],
  reset: ["#QuickAccess_Tab_Perf_ResetToDefault", "ResetCurrentPerfProfileSettings"],
};

const sourceOf = (candidate: unknown): string => {
  if (typeof candidate !== "function") return "";
  try {
    return candidate.toString();
  } catch {
    return "";
  }
};

const uniquelyMatching = (
  candidates: unknown[],
  tokens: readonly string[],
): SteamPerformanceComponent | undefined => {
  const matches = candidates.filter((candidate) => {
    const source = sourceOf(candidate);
    return source.length > 0 && tokens.every((token) => source.includes(token));
  });
  return matches.length === 1 ? matches[0] as SteamPerformanceComponent : undefined;
};

export function selectSteamPerformanceComponents(
  moduleExports: Record<string, unknown>,
): SteamPerformanceComponents {
  const candidates = [...new Set(Object.values(moduleExports))];
  const matches = new Map<SteamPerformanceComponentId, SteamPerformanceComponent>();
  for (const [id, tokens] of Object.entries(SIGNATURES) as Array<[
    SteamPerformanceComponentId,
    readonly string[],
  ]>) {
    const component = uniquelyMatching(candidates, tokens);
    if (component) matches.set(id, component);
  }
  const usage = new Map<SteamPerformanceComponent, number>();
  for (const component of matches.values()) {
    usage.set(component, (usage.get(component) ?? 0) + 1);
  }
  const selected: SteamPerformanceComponents = {};
  for (const [id, component] of matches) {
    if (usage.get(component) === 1) selected[id] = component;
  }
  return selected;
}

export function performanceLayoutFromStore(
  store: SteamPerformanceStoreView,
): SteamPerformanceLayout | null {
  if (!store.msgLimits) return null;
  return {
    frameRate: store.msgLimits.disable_refresh_rate_management === true
      ? "app_target"
      : "legacy",
    splitScaling: store.msgLimits.is_split_scaling_and_filtering_supported === true,
  };
}

const row = (
  components: SteamPerformanceComponents,
  id: SteamPerformanceComponentId,
): SteamPerformanceRow | null => {
  const Component = components[id];
  return Component ? { id, Component } : null;
};

export function composeSteamPerformanceRows(
  components: SteamPerformanceComponents,
  layout: SteamPerformanceLayout,
): SteamPerformanceRow[] {
  const frameRows: SteamPerformanceComponentId[] = layout.frameRate === "app_target"
    ? ["appFrameRate", "disableFrameLimit"]
    : ["legacyFrameRate", "refreshRate"];
  const scalingRows: SteamPerformanceComponentId[] = layout.splitScaling
    ? ["scalingMode", "splitScalingFilter"]
    : ["combinedScaling"];
  const ids: SteamPerformanceComponentId[] = [
    "profile",
    ...frameRows,
    "variableResolution",
    "vrr",
    "allowTearing",
    ...scalingRows,
    "fsrSharpness",
    "nisSharpness",
    "reset",
  ];
  return ids.flatMap((id) => {
    const resolved = row(components, id);
    return resolved ? [resolved] : [];
  });
}
