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
  rpm: number | null; // null = speed unknown this read (e.g. a sensor glitch)
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
  // Coarse mode-based device (Legion Go S): no freeform curve is possible, only
  // quiet/balanced/performance fan modes. When true the editor shows mode chips and
  // hides the graph/adaptive/custom modes. `mode` is the live firmware mode (0/1/2).
  mode_based: boolean;
  mode: number | null;
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

// ---- Battery (Sistema) ----------------------------------------------------
// Every field is nullable: the device may not expose it, and we never fake a
// value (a hidden stat beats a wrong one).
export interface BatteryInfo {
  present: boolean;
  percent: number | null;
  // Charging | Discharging | Full | Not charging | Unknown
  status: string | null;
  health_percent: number | null;
  cycle_count: number | null;
  energy_now_mwh: number | null;
  energy_full_mwh: number | null;
  energy_full_design_mwh: number | null;
  power_now_w: number | null;
  eta_seconds: number | null;
  ac_online: boolean | null;
}

export interface ChargeLimit {
  supported: boolean;
  // false = fixed firmware cap (on/off only, no slider — e.g. Lenovo conservation)
  adjustable: boolean;
  enabled: boolean;
  percent: number;
  min: number;
  max: number;
}

export interface BatteryState {
  battery: BatteryInfo;
  charge_limit: ChargeLimit;
}

export const getBatteryState = callable<[], BatteryState>("get_battery_state");
export const setChargeLimit =
  callable<[enabled: boolean, percent: number], ChargeLimit>("set_charge_limit");

// ---- CPU (Sistema) --------------------------------------------------------
export interface CpuToggle {
  supported: boolean;
  enabled: boolean;
}

export interface CpuState {
  chip: string;
  cores: number | null;
  threads: number | null;
  base_khz: number | null;
  max_khz: number | null;
  smt: CpuToggle;
  boost: CpuToggle;
  // Active physical cores. cores_supported=false → the control is hidden.
  cores_supported: boolean;
  max_cores: number | null;
  active_cores: number | null;
}

export const getCpuState = callable<[], CpuState>("get_cpu_state");
export const setSmt = callable<[enabled: boolean], CpuState>("set_smt");
export const setCpuBoost = callable<[enabled: boolean], CpuState>("set_cpu_boost");
export const setActiveCores = callable<[count: number], CpuState>("set_active_cores");

// ---- Download mode (low power) --------------------------------------------
export interface EcoState {
  enabled: boolean;
  tdp_min_w: number;
  affects_boost: boolean;
  // Brightness % to wake back to (the pre-eco snapshot).
  wake_brightness: number;
}

export const getEcoState = callable<[], EcoState>("get_eco_state");
export const setEco = callable<[enabled: boolean, current_brightness: number], EcoState>("set_eco");

// ── Self-updater — append to src/api.ts (it already imports { callable } from "@decky/api") ──

export interface UpdateInfo {
  current: string;
  latest: string;
  has_update: boolean;
  notes: string;
  download_url: string;
  error: string;
}

export interface InstallResult {
  ok: boolean;
  needs_restart: boolean;
  message: string;
}

export const checkUpdate = callable<[force: boolean], UpdateInfo>("check_update");
export const installUpdate = callable<[], InstallResult>("install_update");
export const restartLoader = callable<[], void>("restart_loader");

// ---- Pantalla (panel color via gamescope) ---------------------------------
// Saturation is PER-GAME (global + per-appid); the calibration fields
// (temperature/contrast) are panel-level → GLOBAL. See ColorPreset for ranges.
export interface ColorPreset {
  saturation: number;   // 0..200, 100 neutral (per-game)
  temperature: number;  // -100 cool .. +100 warm, 0 neutral (global)
  contrast: number;     // -100 flat .. +100 punchy, 0 neutral (global)
}

export interface ColorState extends ColorPreset {
  // False when the host has no gamescope color control → UI shows an honest note.
  supported: boolean;
  global_saturation: number;
  has_game_profile: boolean;
  appid: string | null;
  // The one-tap per-model "OLED look" preset, or null on a real OLED panel.
  oled_look: ColorPreset | null;
  panel: string; // "lcd" | "oled"
  // A calibration change is previewed live but pending confirmation — it
  // auto-reverts to the saved value after `revert_seconds` unless confirmed.
  preview: boolean;
  revert_seconds: number;
  // True when an active look costs a bit of extra power on this device (Intel forces
  // gamescope composition so the look shows in-game) → the UI notes it (by name).
  perf_cost: boolean;
  device_name: string;
}

// ---- GPU clock (Potencia) -------------------------------------------------
export interface GpuClockState {
  supported: boolean;
  manual: boolean;
  range_min: number | null;
  range_max: number | null;
  min: number | null;
  max: number | null;
}

export const getGpuClock = callable<[], GpuClockState>("get_gpu_clock");
export const setGpuClock =
  callable<[min_mhz: number, max_mhz: number], GpuClockState>("set_gpu_clock");
export const setGpuClockAuto = callable<[], GpuClockState>("set_gpu_clock_auto");

export const getColorState = callable<[], ColorState>("get_color_state");
export const setSaturation =
  callable<[value: number, scope: Scope, appid: string | null], ColorState>("set_saturation");
// Preview calibration live (arms the backend auto-revert); confirm with setCalibration.
export const previewCalibration =
  callable<[temperature: number, contrast: number], ColorState>("preview_calibration");
export const setCalibration =
  callable<[temperature: number, contrast: number], ColorState>("set_calibration");
export const applyOledLook = callable<[], ColorState>("apply_oled_look");
export const resetColor = callable<[], ColorState>("reset_color");
