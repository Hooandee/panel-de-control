import { callable } from "@decky/api";

// callable<[arg types], ReturnType>("exact_backend_method_name")
// Names must match the Python `async def` on the Plugin class exactly.
export const getVersion = callable<[], string>("get_version");

export interface DeviceInfo {
  key: string;
  display_name: string;
  chip: string;
  vendor: "amd" | "intel";
  tdp_min: number;
  tdp_default: number;
  tdp_max: number;
  tdp_max_charger: number;
  is_generic: boolean;
}

export const getDevice = callable<[], DeviceInfo>("get_device");

export interface TdpLimits {
  min: number;
  default: number;
  max: number;
  max_ac: number;
}

export interface LevelBound {
  min: number;
  max: number;
}

export interface Levels {
  pl1: number;
  pl2: number;
  pl3: number;
}

export interface TdpState {
  supported: boolean;
  backend: string;
  limits: TdpLimits;
  on_ac: boolean;
  appid: string | null;
  has_game_profile: boolean;
  watts: number;
  global_watts: number;
  applied_w: number | null;
  supports_advanced: boolean;
  level_limits: { pl1?: LevelBound; pl2?: LevelBound; pl3?: LevelBound };
  levels: Levels;
  auto: boolean;
  global_levels: Levels;
  global_auto: boolean;
  // The learned TDP band for the current game (honest reasons when not enough data).
  // Powers the separate "Aprendí…" suggestion (apply a fixed value); auto-TDP itself
  // is parameter-free and decoupled from this band.
  learned: TdpLearned;
}

export interface TdpLearned {
  floor: number | null;
  ceil: number | null;
  seed: number | null;
  observed_lo: number | null;
  observed_hi: number | null;
  enough: boolean;
  // disabled | no_game | no_data | too_few | one_level | error | ok
  reason: string;
  minutes: number;
  target_minutes: number;
}

export interface TdpApplyResult {
  requested_w: number;
  applied_w: number | null;
  ok: boolean;
  detail: string;
}

// Profile scope shared by the TDP and fan-curve features (and the ProfileSelector
// that both reuse).
export type Scope = "global" | "game";
export type TdpScope = Scope;

export interface FanInfo {
  label: string;
  rpm: number;
  percent: number | null;
}

export interface TempInfo {
  label: string;
  celsius: number;
}

export interface FanState {
  supported: boolean;
  fans: FanInfo[];
  temps: TempInfo[];
}

export const getFanState = callable<[], FanState>("get_fan_state");

export const getTdpState = callable<[], TdpState>("get_tdp_state");
export const setTdpWatts = callable<[watts: number, scope: TdpScope, appid: string | null], TdpApplyResult>("set_tdp_watts");
export const createGameProfile = callable<[appid: string], void>("create_game_profile");
export const setCurrentGame = callable<[appid: string | null], TdpState>("set_current_game");
export const setTdpLevels = callable<[off2: number, off3: number, scope: TdpScope, appid: string | null], TdpApplyResult>("set_tdp_levels");
// Returns the full new TDP state so the UI updates badge + sliders in one round-trip.
export const resetTdpAuto = callable<[scope: TdpScope, appid: string | null], TdpState>("reset_tdp_auto");

export interface PowerDraw {
  watts: number | null;
  gpu_busy: number | null;
  auto_tdp: boolean;
  setpoint: number | null;
  // True only while the QAM-open responsive floor is REALLY raising PL1 above where
  // the auto loop would park it → the arc shows a menu-temporary value, so say so.
  ui_floor_engaged: boolean;
}

export const getPowerDraw = callable<[], PowerDraw>("get_power_draw");
export const setAutoTdp = callable<[enabled: boolean], { auto_tdp: boolean }>("set_auto_tdp");
// Signals the QAM panel opened/closed so the auto loop can raise its floor (and bump
// PL1 immediately) to keep the CPU-bound menu render fluid.
export const setUiActive = callable<[enabled: boolean], boolean>("set_ui_active");

export type FanScope = Scope;
// "adaptive" = the learned curve (computed live from telemetry). Choosing it IS
// the opt-in to auto-learning for that scope.
export type FanPreset = "auto" | "adaptive" | "silent" | "balanced" | "performance" | "custom";

export interface FanPresetDef {
  id: "silent" | "balanced" | "performance";
  points: [number, number][];
}

export interface FanCurveState {
  supported: boolean;
  source: string | null;
  pwm_max: number;
  preset: FanPreset;
  points: [number, number][] | null;
  // Silence↔cool bias for the adaptive mode (-100..100, 0 otherwise).
  bias: number;
  global_preset: FanPreset;
  global_points: [number, number][] | null;
  has_game_profile: boolean;
  appid: string | null;
  presets: FanPresetDef[];
}

export const getTelemetryEnabled = callable<[], boolean>("get_telemetry_enabled");
export const setTelemetryEnabled = callable<[enabled: boolean], boolean>("set_telemetry_enabled");
// Wipe all learned usage data (start from scratch). Doesn't touch manual profiles.
export const resetTelemetry = callable<[], boolean>("reset_telemetry");

// Capability + opt-in snapshot for the persistent learning banner. Reports what
// THIS device can actually learn (never-fake: no fan tag if it can't write curves).
export interface LearningStatus {
  telemetry_enabled: boolean;
  tdp_supported: boolean;
  fan_supported: boolean;
}

export const getLearningStatus = callable<[], LearningStatus>("get_learning_status");

export const getUnlockBatteryMax = callable<[], boolean>("get_unlock_battery_max");
export const setUnlockBatteryMax = callable<[enabled: boolean], boolean>("set_unlock_battery_max");

// Opt-in (default off): raise TDP while the QAM is open for a fluid menu. Off keeps
// the auto loop showing the REAL in-game TDP (no menu-time inflation).
export const getQamTdpBoost = callable<[], boolean>("get_qam_tdp_boost");
export const setQamTdpBoost = callable<[enabled: boolean], boolean>("set_qam_tdp_boost");

export const getFanCurveState = callable<[], FanCurveState>("get_fan_curve_state");
export const setFanPreset =
  callable<[preset: FanPreset, scope: FanScope, appid: string | null], FanCurveState>("set_fan_preset");
export const setFanCurvePoints =
  callable<[points: [number, number][], scope: FanScope, appid: string | null], FanCurveState>("set_fan_curve_points");
export const setFanCurveAuto =
  callable<[scope: FanScope, appid: string | null], FanCurveState>("set_fan_auto");
// Adaptive (learned) mode. Selecting it drives the learned curve (or firmware auto
// until enough data). The bias variant sets the silence↔cool dial for the mode.
export const setFanAdaptive =
  callable<[scope: FanScope, appid: string | null], FanCurveState>("set_fan_adaptive");
export const setFanAdaptiveBias =
  callable<[bias: number, scope: FanScope, appid: string | null], FanCurveState>("set_fan_adaptive_bias");

// F3 — fan-curve suggestion fit to a game's observed temperature band.
export interface FanSuggestion {
  available: boolean;
  // ok | disabled | unsupported | no_game | no_data | too_few | flat | error
  reason: string;
  minutes: number;
  target_minutes: number;
  // Raw in-game dwell (and target), so the UI derives the learning bar + "min left"
  // honestly at the round-up boundary rather than from rounded minutes.
  seconds: number;
  target_seconds: number;
  band: { floor: number; typical: number; high: number; peak: number } | null;
  curves: { quiet: [number, number][]; balanced: [number, number][]; cool: [number, number][] } | null;
}

export const getFanSuggestion =
  callable<[appid: string | null], FanSuggestion>("get_fan_suggestion");
