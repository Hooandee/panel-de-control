import { recordSteamPerformanceDiagnostic } from "./performanceDiagnostics";
import type { SteamPerformanceComponentId } from "./performanceSurface";

export interface PerfSettingsStore {
  nCurrentGameID?: unknown;
  nActiveProfileGameID?: unknown;
  msgSettingsPerApp?: Record<string, unknown>;
  msgSettingsGlobal?: Record<string, unknown>;
  msgLimits?: Record<string, unknown>;
  SetFPSLimit?: (external: boolean, value: number) => unknown;
  SetDisplayRefreshRateManualHz?: (external: boolean, value: number) => unknown;
  SetScalingFilter?: (value: number) => unknown;
  SetNISSharpness?: (value: number) => unknown;
  SetFSRSharpness?: (value: number) => unknown;
  SetSplitScalingFilter?: (value: number) => unknown;
  SetSplitScalingScaler?: (value: number) => unknown;
  SetVRREnabled?: (value: boolean) => unknown;
  ResetCurrentPerfProfileSettings?: () => unknown;
}

export type ClientPerformanceSetting = "gamescope_app_target_framerate" | "gamescope_disable_framelimit"
  | "gamescope_enable_app_target_framerate" | "gamescope_allow_tearing" | "steamos_vrs_enabled";

export interface PerformanceSettingsDeps {
  store: () => PerfSettingsStore | null;
  runningGameId: () => number | null;
  settings?: {
    get: (name: ClientPerformanceSetting) => unknown;
    set: (name: ClientPerformanceSetting, value: number | boolean) => unknown;
  };
  display: () => { external: boolean; isVrrCapable?: boolean; supportedRefreshRates?: number[] } | null;
  gamescope: () => {
    is_app_refresh_rate_supported?: boolean;
    is_refresh_rate_switching_restricted?: boolean;
    active_display_info?: { supported_frame_rates?: number[]; supported_refresh_rates?: number[] };
  } | null;
  steamOs: () => { is_vrs_available?: boolean } | null;
}

export type PerformanceSettingControl = { id: SteamPerformanceComponentId } & (
  | { kind: "toggle"; value: boolean }
  | { kind: "slider"; value: number; min: number; max: number; step: number }
  | { kind: "options"; value: number; options: Array<{ value: number; label: string; refreshHz?: number }> }
  | { kind: "action" }
);
export interface PerformanceEditContext { scope: "global" | "game"; runningGameId: number | null }
export type PerformanceWriteStatus = "request_sent" | "unchanged" | "unavailable" | "context_mismatch" | "invalid_value" | "failed";

type Binding = { control: PerformanceSettingControl; write: (value?: number | boolean) => unknown };
const numeric = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const numbers = (value: unknown): number[] => Array.isArray(value) && value.length > 0
  && value.length <= 1000 && value.every((item) => numeric(item) && Number.isInteger(item) && item >= 0)
  ? [...new Set(value)] : [];
const FILTERS: Record<number, string> = { 1: "linear", 2: "nearest", 3: "sharp", 4: "nis" };
const COMBINED_FILTERS: Record<number, string> = { 4: "linear", 2: "nearest", 3: "integer", 1: "fsr", 5: "nis" };
const SCALERS: Record<number, string> = { 1: "auto", 2: "integer", 3: "fit", 4: "fill", 5: "stretch" };

export function steamRefreshRateForFps(fps: number, rates: number[]): number | undefined {
  if (!numeric(fps) || fps <= 0 || !rates.length) return undefined;
  for (let multiplier = Math.min(Math.ceil(Math.max(...rates) / fps), 100); multiplier > 0; multiplier--) {
    const hz = fps * multiplier;
    if (rates.includes(hz)) return hz;
  }
  return undefined;
}

function readSource<T>(source: string, read: () => T, fallback: T): T {
  try {
    const value = read();
    recordSteamPerformanceDiagnostic(`read_${source}`, { status: "available", control_id: source });
    return value;
  } catch {
    recordSteamPerformanceDiagnostic(`read_${source}`, { status: "read_failed", control_id: source });
    return fallback;
  }
}

function bindings(deps: PerformanceSettingsDeps): Binding[] {
  const store = readSource("store", deps.store, null);
  if (!store) return [];
  const settings = readSource("settings", () => store.msgSettingsPerApp ?? {}, {});
  const limits = readSource("limits", () => store.msgLimits ?? {}, {});
  const display = readSource("display", deps.display, null);
  const result: Binding[] = [];
  const options = (id: SteamPerformanceComponentId, value: unknown, values: number[], write: Binding["write"], labels?: Record<number, string>) => {
    const allowed = labels ? values.filter((item) => labels[item] !== undefined) : values;
    if (numeric(value) && allowed.includes(value)) result.push({
      control: { id, kind: "options", value, options: allowed.map((item) => ({ value: item, label: labels?.[item] ?? String(item) })) }, write,
    });
  };
  const toggle = (id: SteamPerformanceComponentId, value: unknown, write: Binding["write"]) => {
    if (typeof value === "boolean") result.push({ control: { id, kind: "toggle", value }, write });
  };
  readSource("legacyFrameRate", () => {
    if (display && limits.disable_refresh_rate_management === false && store.SetFPSLimit) {
      options("legacyFrameRate", settings[display.external ? "fps_limit_external" : "fps_limit"],
        numbers(limits[display.external ? "fps_limit_options_external" : "fps_limit_options"]),
        (value) => store.SetFPSLimit!(display.external, value as number));
    }
  }, undefined);
  readSource("refreshRate", () => {
    if (display && store.SetDisplayRefreshRateManualHz && limits.is_manual_display_refresh_rate_available === true
      && (display.external ? store.msgSettingsGlobal?.allow_external_display_refresh_control === true : limits.disable_refresh_rate_management === false)) {
      const prefix = display.external ? "display_external_refresh_manual_hz" : "display_refresh_manual_hz";
      const min = limits[`${prefix}_min`], max = limits[`${prefix}_max`];
      let values = numbers(display.supportedRefreshRates);
      if (!values.length && numeric(min) && numeric(max) && Number.isInteger(min) && Number.isInteger(max)
        && min > 0 && max >= min && max - min < 1000) values = Array.from({ length: max - min + 1 }, (_, i) => min + i);
      options("refreshRate", settings[prefix], values, (value) => store.SetDisplayRefreshRateManualHz!(display.external, value as number));
    }
  }, undefined);
  const legacyScaling = () => limits.is_split_scaling_and_filtering_supported !== true
    && typeof store.SetScalingFilter === "function" && numeric(settings.scaling_filter);
  const splitScaling = () => limits.is_split_scaling_and_filtering_supported !== false && !legacyScaling();
  readSource("combinedScaling", () => {
    if (legacyScaling()) options("combinedScaling", settings.scaling_filter,
      limits.is_nis_supported === true ? [4, 2, 3, 1, 5] : [4, 2, 3, 1],
      (next) => store.SetScalingFilter!(next as number), COMBINED_FILTERS);
  }, undefined);
  readSource("splitScalingFilter", () => {
    if (splitScaling() && store.SetSplitScalingFilter) options("splitScalingFilter", settings.split_scaling_filter,
      numbers(limits.split_scaling_filters_available), (value) => store.SetSplitScalingFilter!(value as number), FILTERS);
  }, undefined);
  readSource("scalingMode", () => {
    if (splitScaling() && store.SetSplitScalingScaler) options("scalingMode", settings.split_scaling_scaler,
      numbers(limits.split_scaling_scalers_available), (value) => store.SetSplitScalingScaler!(value as number), SCALERS);
  }, undefined);
  readSource("sharpness", () => {
    const min = limits.fsr_sharpness_min, max = limits.fsr_sharpness_max, value = settings.fsr_sharpness;
    if (splitScaling() && settings.split_scaling_filter === 3 && store.SetFSRSharpness && numeric(min) && numeric(max) && numeric(value)
      && Number.isInteger(min) && Number.isInteger(max) && Number.isInteger(value) && min >= 0 && max >= min && value >= min && value <= max) {
      result.push({ control: { id: "sharpness", kind: "slider", value, min, max, step: 1 }, write: (next) => store.SetFSRSharpness!(next as number) });
    }
  }, undefined);
  readSource("fsrSharpness", () => {
    const min = limits.fsr_sharpness_min, max = limits.fsr_sharpness_max, value = settings.fsr_sharpness;
    if (legacyScaling() && settings.scaling_filter === 1 && store.SetFSRSharpness && numeric(min) && numeric(max) && numeric(value)
      && Number.isInteger(min) && Number.isInteger(max) && Number.isInteger(value) && min >= 0 && max >= min && value >= min && value <= max) {
      result.push({ control: { id: "fsrSharpness", kind: "slider", value, min, max, step: 1 }, write: (next) => store.SetFSRSharpness!(next as number) });
    }
  }, undefined);
  readSource("nisSharpness", () => {
    const min = limits.nis_sharpness_min, max = limits.nis_sharpness_max, value = settings.nis_sharpness;
    const selected = legacyScaling() ? settings.scaling_filter === 5 && limits.is_nis_supported === true
      : splitScaling() && settings.split_scaling_filter === 4 && numbers(limits.split_scaling_filters_available).includes(4);
    if (selected && store.SetNISSharpness && numeric(min) && numeric(max) && numeric(value)
      && Number.isInteger(min) && Number.isInteger(max) && Number.isInteger(value) && min >= 0 && max >= min && value >= min && value <= max) {
      result.push({ control: { id: "nisSharpness", kind: "slider", value, min, max, step: 1 }, write: (next) => store.SetNISSharpness!(next as number) });
    }
  }, undefined);
  readSource("vrr", () => {
    if (display?.isVrrCapable === true && limits.is_vrr_supported === true && store.SetVRREnabled) {
      toggle("vrr", settings.is_vrr_enabled, (next) => store.SetVRREnabled!(next as boolean));
    }
  }, undefined);
  const client = deps.settings;
  if (client) {
    readSource("allowTearing", () => {
      toggle("allowTearing", client.get("gamescope_allow_tearing"), (next) => client.set("gamescope_allow_tearing", next as boolean));
    }, undefined);
    readSource("variableResolution", () => {
      if (deps.steamOs()?.is_vrs_available === true) toggle("variableResolution", client.get("steamos_vrs_enabled"), (next) => client.set("steamos_vrs_enabled", next as boolean));
    }, undefined);
    const frameRateAvailable = () => limits.disable_refresh_rate_management === true
      && deps.gamescope()?.is_app_refresh_rate_supported === true
      && client.get("gamescope_enable_app_target_framerate") === true;
    readSource("disableFrameLimit", () => {
      if (frameRateAvailable()) toggle("disableFrameLimit", client.get("gamescope_disable_framelimit"), (next) => client.set("gamescope_disable_framelimit", next as boolean));
    }, undefined);
    readSource("appFrameRate", () => {
      if (!frameRateAvailable()) return;
      const gs = deps.gamescope();
      if (client.get("gamescope_disable_framelimit") === false && display && gs && (display.external || gs.is_refresh_rate_switching_restricted === false)) {
        let rates = numbers(gs.active_display_info?.supported_frame_rates);
        if (settings.is_vrr_enabled === true && rates.length) {
          const low = Math.min(...rates), high = Math.max(...rates);
          rates = high - low < 1000 ? Array.from({ length: high - low + 1 }, (_, i) => low + i) : [];
        }
        options("appFrameRate", client.get("gamescope_app_target_framerate"), rates,
          (next) => client.set("gamescope_app_target_framerate", next as number));
        const frameRate = result.find((binding) => binding.control.id === "appFrameRate")?.control;
        if (frameRate?.kind === "options" && settings.is_vrr_enabled !== true) {
          const refreshRates = numbers(gs.active_display_info?.supported_refresh_rates);
          frameRate.options = frameRate.options.map((option) => ({
            ...option, refreshHz: steamRefreshRateForFps(option.value, refreshRates),
          }));
        }
      }
    }, undefined);
  }
  readSource("reset", () => {
    if (store.ResetCurrentPerfProfileSettings) result.push({ control: { id: "reset", kind: "action" }, write: () => store.ResetCurrentPerfProfileSettings!() });
  }, undefined);
  return result;
}

export function readPerformanceSettings(deps: PerformanceSettingsDeps): PerformanceSettingControl[] {
  try { return bindings(deps).map(({ control }) => control); } catch { return []; }
}

const profileId = (value: unknown): bigint | null => {
  if (typeof value !== "string" && typeof value !== "number") return null;
  if (typeof value === "number" && !Number.isSafeInteger(value)) return null;
  if (!/^[1-9][0-9]*$/.test(String(value))) return null;
  try { const id = BigInt(value); return id <= BigInt("18446744073709551615") ? id : null; } catch { return null; }
};
function matchesContext(deps: PerformanceSettingsDeps, context: PerformanceEditContext): boolean {
  if (deps.runningGameId() !== context.runningGameId) return false;
  const store = deps.store();
  const current = profileId(store?.nCurrentGameID), active = profileId(store?.nActiveProfileGameID);
  if (current === null || active === null) return false;
  const global = BigInt(769);
  if (context.runningGameId === null) return context.scope === "global" && active === global;
  const id = context.runningGameId;
  if (!Number.isInteger(id) || id <= 0 || id > 0xffffffff || current === global) return false;
  const appid = current <= BigInt(0xffffffff) ? current
    : ((current >> BigInt(24)) & BigInt(255)) === BigInt(2)
      ? (current >> BigInt(32)) & BigInt(0xffffffff) : current & BigInt(0xffffff);
  return appid === BigInt(id) && active === (context.scope === "global" ? global : current);
}

export async function writePerformanceSetting(
  deps: PerformanceSettingsDeps, context: PerformanceEditContext,
  id: SteamPerformanceComponentId, value?: number | boolean,
): Promise<{ status: PerformanceWriteStatus }> {
  try {
    if (!matchesContext(deps, context)) return { status: "context_mismatch" };
    const binding = bindings(deps).find(({ control }) => control.id === id);
    if (!binding) return { status: "unavailable" };
    const control = binding.control;
    const valid = control.kind === "action" ? value === undefined
      : control.kind === "toggle" ? typeof value === "boolean"
        : numeric(value) && (control.kind === "options" ? control.options.some((option) => option.value === value)
          : value >= control.min && value <= control.max && Number.isInteger((value - control.min) / control.step));
    if (!valid) return { status: "invalid_value" };
    if (control.kind !== "action" && control.value === value) return { status: "unchanged" };
    if (!matchesContext(deps, context)) return { status: "context_mismatch" };
    await binding.write(value);
    return { status: "request_sent" };
  } catch { return { status: "failed" }; }
}
