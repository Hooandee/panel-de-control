import { callable } from "@decky/api";
import type { LaunchTools } from "./launch/catalog";

// callable<[arg types], ReturnType>("exact_backend_method_name")
// Names must match the Python `async def` on the Plugin class exactly.
export const getVersion = callable<[], string>("get_version");

// Detected host tools (lsfg/mangohud/gamemode/…) + distro for the launch-options
// pills. LaunchTools is defined in the pure catalog module (no @decky import).
export type { LaunchTools };
export const getLaunchTools = callable<[], LaunchTools>("get_launch_tools");
// Which PROTON_* vars the game's Proton build actually supports (read from its
// script) → gate version-specific pills honestly. `found` false = the build wasn't
// located (native/non-Steam/missing), and then `envs` is empty — no unconfirmed options.
export interface ProtonCaps {
  envs: string[];
  found: boolean;
}
export const getProtonCaps = callable<[compatName: string], ProtonCaps>("get_proton_caps");
// Pill usage counts ({pill_id: times applied}) → the editor surfaces the most-used.
export const getLaunchUsage = callable<[], Record<string, number>>("get_launch_usage");
export const bumpLaunchUsage = callable<[ids: string[]], boolean>("bump_launch_usage");
// User-defined launch-variable library (env / game args). set_* returns the stored
// (shape-coerced) list.
import type { CustomVarDef } from "./launch/customVars";
export type { CustomVarDef };
export const getCustomLaunchVars = callable<[], CustomVarDef[]>("get_custom_launch_vars");
export const setCustomLaunchVars = callable<[vars: CustomVarDef[]], CustomVarDef[]>("set_custom_launch_vars");

// Durable mirror of the frontend's localStorage prefs (a null value removes a key).
export const getUiPrefs = callable<[], Record<string, string>>("get_ui_prefs");
export const setUiPrefs = callable<[Record<string, string | null>], boolean>("set_ui_prefs");

// Durable module enable/disable state. `disabled` = the user-disabled set (generic
// ids + power/learning folded in). set_ui_module returns the fresh set after applying.
export const getUiModules = callable<[], { disabled: string[] }>("get_ui_modules");
export const setUiModule = callable<[string, boolean], { disabled: string[] }>("set_ui_module");
export const resetUiModules = callable<[], { disabled: string[] }>("reset_modules");

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
  // When true, the shell shows the experimental marker for this recognised model.
  experimental: boolean;
  cooler_max: number | null;
  // GPU generation ("rdna2"|"rdna3"|"rdna35"|"rdna4"|"intel"|"unknown") for the
  // launch-options upscaler gating (FSR4 = rdna3/rdna4).
  gpu_gen: string;
  // When true, the charger headroom (tdp_max_charger above tdp_max) is only reachable
  // with the charger connected — the firmware caps the sustained limit on battery. Hide
  // the "raise on battery" toggle; the arc shows the locked charger segment instead.
  charger_only_extra: boolean;
}

export const getDevice = callable<[], DeviceInfo>("get_device");

// Generic (unrecognised) or experimental (recognised, unconfirmed): both drive the
// header badge and the Ajustes note.
export const isUnvalidated = (d: DeviceInfo): boolean => d.is_generic || d.experimental;

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

// Boost behaviour: how the SPPT/FPPT rails relate to the sustained PL1.
//   estable — flat (SPPT = FPPT = PL1), the default; "what you set is what it draws".
//   auto    — managed headroom (SPPT ≈ 1.2x, FPPT ≈ 1.4x), clamped to firmware max.
//   custom  — explicit additive margins (the offset sliders).
export type BoostMode = "estable" | "auto" | "custom";

export interface TdpState {
  supported: boolean;
  backend: string;
  limits: TdpLimits;
  on_ac: boolean;
  appid: string | null;
  has_game_profile: boolean;
  // True when this game applies the global profile (no own value, or its own is toggled
  // to follow global). Its stored values are never deleted.
  follows_global: boolean;
  watts: number;
  global_watts: number;
  applied_w: number | null;
  supports_advanced: boolean;
  level_limits: { pl1?: LevelBound; pl2?: LevelBound; pl3?: LevelBound };
  levels: Levels;
  boost_mode: BoostMode;
  global_levels: Levels;
  global_boost_mode: BoostMode;
  // The learned TDP band for the current game (honest reasons when not enough data).
  // Powers the separate "Aprendí…" suggestion (apply a fixed value); auto-TDP itself
  // is parameter-free and decoupled from this band.
  learned: TdpLearned;
  // Quick-preset watts for the arc buttons (curated per-model or derived from limits).
  presets: TdpPresets;
  // Firmware performance modes (e.g. low-power/balanced/performance/custom); empty
  // hides the selector. firmware_mode is the active one ("custom" = our TDP slider).
  firmware_modes: string[];
  firmware_mode: string;
  // True when get_tdp_state adopted an external (HHD/Steam) TDP change on this read.
  external_change: boolean;
  // Master switch: when false we stop writing rails → Potencia drops to monitor-only.
  tdp_control_enabled: boolean;
  // One-time full-screen notices already shown (durable across reboot).
  seen_autotdp_notice: boolean;
  seen_tdp_conflict_takeover: boolean;
}

export interface TdpPresets {
  quiet: number;
  balanced: number;
  turbo: number;    // on battery
  turbo_ac: number; // on charger
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
// Sets the boost mode; returns the full new TDP state so the UI updates the segmented
// control + rails in one round-trip.
export const setTdpBoostMode = callable<[mode: BoostMode, scope: TdpScope, appid: string | null], TdpState>("set_tdp_boost_mode");
// Firmware performance mode (Legion Go original). Device-global; returns fresh state.
export const setTdpFirmwareMode = callable<[mode: string], TdpState>("set_tdp_firmware_mode");

// Toggle a game between its own TDP profile and following the global one (never deletes
// the game's stored values). Returns the full new state.
export const setTdpFollowGlobal = callable<[follow: boolean, appid: string | null], TdpState>("set_tdp_follow_global");

export interface PowerDraw {
  watts: number | null;
  gpu_busy: number | null;
  auto_tdp: boolean;
  setpoint: number | null;
  // Live PL1 the firmware actually holds (reflects download mode + external HHD/Steam
  // changes + chip clamp). null when the backend can't read it back.
  applied: number | null;
  // True only while the QAM-open responsive floor is REALLY raising PL1 above where
  // the auto loop would park it → the arc shows a menu-temporary value, so say so.
  ui_floor_engaged: boolean;
  // Live charger state, polled every second so the UI can refresh the slider ceiling
  // (battery vs charger) the instant the charger is plugged or unplugged.
  on_ac: boolean;
}

export const getPowerDraw = callable<[], PowerDraw>("get_power_draw");
export const setAutoTdp = callable<[enabled: boolean, scope: TdpScope, appid: string | null], { auto_tdp: boolean }>("set_auto_tdp");
// Signals the QAM panel opened/closed so the auto loop can raise its floor (and bump
// PL1 immediately) to keep the CPU-bound menu render fluid.
export const setUiActive = callable<[enabled: boolean], boolean>("set_ui_active");

// ---- TDP control / conflict take-over -------------------------------------
// HHD conflict detection lives in the backend (it reads the REST daemon); SDTDP is
// detected on the frontend via Decky's plugin list (see tdp/deckyPlugins.ts).
export const getTdpConflict =
  callable<[], { hhd_present: boolean; hhd_managing: boolean }>("get_tdp_conflict");
// Hand HHD's TDP module over to us (reversible; saves its previous value).
export const takeTdpControl =
  callable<[], { ok: boolean; hhd_managing: boolean }>("take_tdp_control");
// The TDP master switch (get/set_tdp_control_enabled) is driven via the module
// editor now (power module → set_ui_module), so it has no dedicated frontend binding.
// One-time-notice flags (durable, backend-persisted).
export const setSeenAutotdpNotice =
  callable<[seen: boolean], boolean>("set_seen_autotdp_notice");
export const setSeenTdpConflictTakeover =
  callable<[seen: boolean], boolean>("set_seen_tdp_conflict_takeover");

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
  // Software-loop backends can wedge → the UI offers a reset; hardware-curve can't.
  resettable: boolean;
  source: string | null;
  pwm_max: number;
  // Read-only firmware curve (MSI Claw): the device can't be controlled but its
  // firmware fan curve is legible over the EC and shown informationally. Non-null
  // only when unsupported; null everywhere else.
  firmware_points: { temp: number; pct: number }[] | null;
  preset: FanPreset;
  points: [number, number][] | null;
  // Silence↔cool bias for the adaptive mode (-100..100, 0 otherwise).
  bias: number;
  global_preset: FanPreset;
  global_points: [number, number][] | null;
  has_game_profile: boolean;
  // True when this game applies the global fan curve (no own, or toggled to follow).
  follows_global: boolean;
  appid: string | null;
  presets: FanPresetDef[];
  // Experimental EC fan control (Legion Go S): available = the device has the
  // unofficial channel; enabled = the user opted in. When available && !enabled the
  // control card shows the opt-in toggle instead of the editor.
  experimental_available: boolean;
  experimental_enabled: boolean;
  // Set only by reset_fan_control: whether the release to firmware actually landed.
  reset_ok?: boolean;
  // Host OS name (PRETTY_NAME) for the honest "curve not available on this OS"
  // message; null when unreadable.
  os_name: string | null;
  // Active firmware performance mode (Legion Go original) governing the fan, e.g.
  // "performance"; null when in custom / the device has no firmware modes.
  firmware_mode: string | null;
  // True when the device exposes firmware modes at all (even in custom) — the fan
  // can't be curve-controlled here; a TDP mode governs it.
  has_firmware_modes: boolean;
  // Manual full-blast override ("a tope") support + live state (Legion Go original
  // via GZFD full-speed). max_available false → the control is hidden.
  max_available: boolean;
  max_enabled: boolean;
}

// Learning on/off (get/set_telemetry_enabled) is driven via the module editor now
// (learning module → set_ui_module), so it has no dedicated frontend binding.
// Wipe all learned usage data (start from scratch). Doesn't touch manual profiles.
export const resetTelemetry = callable<[], boolean>("reset_telemetry");

// Capability + opt-in snapshot for the persistent learning banner. Reports what
// THIS device can actually learn (no fan tag if it can't write curves).
export interface LearningStatus {
  telemetry_enabled: boolean;
  tdp_supported: boolean;
  fan_supported: boolean;
}

export const getLearningStatus = callable<[], LearningStatus>("get_learning_status");

export const getUnlockBatteryMax = callable<[], boolean>("get_unlock_battery_max");
export const setUnlockBatteryMax = callable<[enabled: boolean], boolean>("set_unlock_battery_max");
export const getCoolerBoost = callable<[], boolean>("get_cooler_boost");
export const setCoolerBoost = callable<[enabled: boolean], boolean>("set_cooler_boost");

// Opt-in (default off): raise TDP while the QAM is open for a fluid menu. Off keeps
// the auto loop showing the REAL in-game TDP (no menu-time inflation).
export const getQamTdpBoost = callable<[], boolean>("get_qam_tdp_boost");
export const setQamTdpBoost = callable<[enabled: boolean], boolean>("set_qam_tdp_boost");

export const getFanCurveState = callable<[], FanCurveState>("get_fan_curve_state");
// Opt in/out of experimental EC fan control (Legion Go S). Returns the fresh state.
export const setFanExperimental =
  callable<[enabled: boolean], FanCurveState>("set_fan_experimental");
export const resetFanControl = callable<[], FanCurveState>("reset_fan_control");
export const setFanPreset =
  callable<[preset: FanPreset, scope: FanScope, appid: string | null], FanCurveState>("set_fan_preset");
export const setFanFollowGlobal =
  callable<[follow: boolean, appid: string | null], FanCurveState>("set_fan_follow_global");
export const setFanCurvePoints =
  callable<[points: [number, number][], scope: FanScope, appid: string | null], FanCurveState>("set_fan_curve_points");
export const setFanCurveAuto =
  callable<[scope: FanScope, appid: string | null], FanCurveState>("set_fan_auto");
// Full-blast override: forces the fan to max now, independent of temperature.
export const getFanMax = callable<[], boolean>("get_fan_max");
export const setFanMax = callable<[enabled: boolean], FanCurveState>("set_fan_max");
// Adaptive (learned) mode. Selecting it drives the learned curve (or firmware auto
// until enough data). The bias variant sets the silence↔cool dial for the mode.
export const setFanAdaptive =
  callable<[scope: FanScope, appid: string | null], FanCurveState>("set_fan_adaptive");
export const setFanAdaptiveBias =
  callable<[bias: number, scope: FanScope, appid: string | null], FanCurveState>("set_fan_adaptive_bias");

// Fan-curve suggestion fit to a game's observed temperature band.
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
// Every field is nullable: the device may not expose it, and we don't fabricate a
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
  // Per-game scope for the CPU controls (SMT/boost/cores): true when this game applies
  // the global CPU profile (no own, or toggled to follow). Own values never deleted.
  follows_global: boolean;
  has_game_profile: boolean;
}

export const getCpuState = callable<[], CpuState>("get_cpu_state");
export const setSmt = callable<[enabled: boolean, scope: TdpScope, appid: string | null], CpuState>("set_smt");
export const setCpuBoost = callable<[enabled: boolean, scope: TdpScope, appid: string | null], CpuState>("set_cpu_boost");
export const setActiveCores = callable<[count: number, scope: TdpScope, appid: string | null], CpuState>("set_active_cores");
export const setCpuFollowGlobal = callable<[follow: boolean, appid: string | null], CpuState>("set_cpu_follow_global");

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
// Saturation is PER-GAME (global + per-appid); every other field is panel-level
// calibration → GLOBAL. See ColorPreset for ranges.
export interface ColorPreset {
  saturation: number;   // 0..200, 100 neutral (per-game)
  temperature: number;  // -100 cool .. +100 warm, 0 neutral (global)
  contrast: number;     // -100 flat .. +100 punchy, 0 neutral (global)
  gamma: number;        // -100 dark .. +100 bright midtones, 0 neutral (global)
  hue: number;          // -100 .. +100 tint rotation, 0 neutral (global)
  black: number;        // -100 deepen .. +100 lift black point, 0 neutral (global)
  gain_r: number;       // 50..150, 100 = 1.0 — manual white balance (global)
  gain_g: number;
  gain_b: number;
  vibrance: number;     // -100 mute .. +100 boost (spares vivid pixels), 0 neutral (global)
}

// Calibration = a ColorPreset minus the per-game saturation. The key list lives in
// display/color.ts (kept free of this module's @decky/api import).
export type Calibration = Omit<ColorPreset, "saturation">;

export interface ColorState extends ColorPreset {
  // False when the host has no gamescope color control → UI shows an honest note.
  supported: boolean;
  global_saturation: number;
  has_game_profile: boolean;
  // True when this game applies the global saturation (no own, or toggled to follow).
  follows_global: boolean;
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
  // One-tap balanced looks available on this panel (native first) + the one the global
  // color currently matches (null = a custom look).
  presets: string[];
  active_preset: string | null;
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
  callable<[min_mhz: number, max_mhz: number, scope: TdpScope, appid: string | null], GpuClockState>("set_gpu_clock");
export const setGpuClockAuto = callable<[scope: TdpScope, appid: string | null], GpuClockState>("set_gpu_clock_auto");

export const getColorState = callable<[], ColorState>("get_color_state");
export const setSaturation =
  callable<[value: number, scope: Scope, appid: string | null], ColorState>("set_saturation");
export const setColorFollowGlobal =
  callable<[follow: boolean, appid: string | null], ColorState>("set_color_follow_global");
// Preview calibration live (arms the backend auto-revert); confirm with setCalibration.
// Both take the full calibration object (backend picks the known fields + clamps).
export const previewCalibration =
  callable<[calibration: Calibration], ColorState>("preview_calibration");
export const setCalibration =
  callable<[calibration: Calibration, scope: Scope, appid: string | null], ColorState>("set_calibration");
export const applyOledLook = callable<[scope: Scope, appid: string | null], ColorState>("apply_oled_look");
export const resetColor = callable<[], ColorState>("reset_color");
// Apply a balanced full-color look to a scope ("native" = back to the panel's own look).
export const applyColorPreset =
  callable<[key: string, scope: Scope, appid: string | null], ColorState>("apply_color_preset");

// ---- Night mode (scheduled warm shift) ------------------------------------
export interface NightState {
  supported: boolean;
  warmth: number;            // 0..100, added-warmth in temperature units
  enabled: boolean;          // master on/off
  schedule_enabled: boolean; // while enabled: true = by time window, false = always
  start: number;             // window start, minute-of-day (0..1439)
  end: number;               // window end, minute-of-day
  active: boolean;           // whether the warm shift is applied right now
}

export interface NightPatch {
  warmth?: number;
  enabled?: boolean;
  schedule_enabled?: boolean;
  start?: number;
  end?: number;
}

export const getNightState = callable<[], NightState>("get_night_state");
export const setNight = callable<[patch: NightPatch], NightState>("set_night");

// ---- HDR output -----------------------------------------------------------
// On/off only: HDR content scans out directly, so its color can't be tuned from here.
export interface HdrState {
  supported: boolean;   // HDR-capable panel + gamescope present
  enabled: boolean;
  // Per-game via the shared color scope: true when this game follows the global HDR.
  follows_global: boolean;
}

export interface HdrPatch {
  enabled?: boolean;
}

export const getHdrState = callable<[], HdrState>("get_hdr_state");
export const setHdr = callable<[patch: HdrPatch, scope: Scope, appid: string | null], HdrState>("set_hdr");

// ---- Mandos (controller manager) ------------------------------------------
export type ControllerTarget = { gamepad: string } | { key: string };

export interface RemapButton {
  // The InputPlumber source capability (e.g. "LeftPaddle1") — used when remapping.
  source: string;
  // The literal silkscreen label printed on the device (e.g. "Y1", "M2"),
  // device-correct from the backend's per-device table. NOT translated.
  label: string;
  // The current override, or null = still at the device default.
  target: ControllerTarget[] | null;
}

export interface ControllerConfig {
  // Which resident daemon owns the gamepad (we cooperate with it, never grab).
  manager: "hhd" | "inputplumber" | "none";
  manager_version: string | null;
  supported: boolean;
  // "remap" = per-button editor (InputPlumber); "settings" = mode/paddles (HHD).
  kind: "remap" | "settings" | "none";
  // remap (InputPlumber)
  // Whether we have a known button map for this model. When false,
  // `buttons` is empty and the UI shows an honest "not calibrated" note.
  device_known?: boolean;
  buttons?: RemapButton[];
  gamepad_targets?: string[];
  key_targets?: string[];
  // Per-game scope (InputPlumber): whether the running game follows the global
  // remap, and whether it has its own saved profile — drive the scope tab.
  follows_global?: boolean;
  has_game_profile?: boolean;
  // settings (HHD)
  device_key?: string;
  mode?: string | null;
  mode_options?: string[];
  paddles_as?: string | null;
  paddles_options?: string[];
}

// ---- Bug reporter ---------------------------------------------------------
// Write-only: the plugin can only SEND a report. On success the backend returns a
// short code the user can quote; on failure it saved the bundle locally.
export interface ReportResult {
  ok: boolean;
  code?: string;
  issue_url?: string | null;
  error?: string;
  saved_path?: string | null;
}

// `context` carries frontend-only diagnostics the backend can't see (e.g. the
// running game's launch-options string + Proton caps for a "launch" report).
export const submitReport =
  callable<[categories: string[], text: string, context: Record<string, unknown>], ReportResult>(
    "submit_report",
  );

export const getControllerConfig = callable<[], ControllerConfig>("get_controller_config");
export const setControllerButton =
  callable<[source: string, targets: ControllerTarget[], scope: Scope, appid: string | null], ControllerConfig>(
    "set_controller_button");
export const setControllerFollowGlobal =
  callable<[follow: boolean, appid: string], ControllerConfig>("set_controller_follow_global");
export const setControllerSetting =
  callable<[field: string, value: string], ControllerConfig>("set_controller_setting");
export const resetController =
  callable<[scope: Scope, appid: string | null], ControllerConfig>("reset_controller");

// ---- Ajustes: per-game profile overview -----------------------------------
// One row per game that has a stored per-game profile in any section (raw own values).
export interface GameProfileRow {
  appid: string;
  tdp?: { pl1: number; auto: boolean; gpu: boolean; follows_global: boolean };
  fan?: { preset: string; follows_global: boolean };
  color?: { saturation: number; calibrated: boolean; hdr: boolean; follows_global: boolean };
  cpu?: { smt: boolean; boost: boolean; cores: number | null; follows_global: boolean };
  mandos?: { count: number; follows_global: boolean };
  audio?: { follows_global: boolean };
}
export const listGameProfiles = callable<[], GameProfileRow[]>("list_game_profiles");
export const resetGameProfiles =
  callable<[appid: string], GameProfileRow[]>("reset_game_profiles");

// ---- Sonido: audio EQ ----------------------------------------------------
export interface AudioPresetDef {
  id: string;
  tuned?: boolean;
}
export interface AudioProfile {
  name: string;
  gains: number[];
  bass: number;
}
export interface AudioState {
  supported: boolean;
  enabled: boolean;
  route: "speaker" | "headphone";
  appid: string | null;
  follows_global: boolean;
  has_game_profile: boolean;
  preset: string;
  gains: number[];
  bass: number;
  loudness: boolean;
  test_playing: boolean;
  test_sample: string | null;
  test_samples: string[];
  presets: AudioPresetDef[];
  profiles: AudioProfile[];
  device_name: string;
  guard: boolean;
  safe_limits: { bands: number[]; bass: number };
}
export const getAudioState = callable<[], AudioState>("get_audio_state");
export const setSpeakerGuard = callable<[enabled: boolean], AudioState>("set_speaker_guard");
export const setAudioEnabled = callable<[enabled: boolean], AudioState>("set_audio_enabled");
export const applyAudioPreset =
  callable<[preset: string, scope: Scope, appid: string | null], AudioState>("apply_audio_preset");
export const setAudioBand =
  callable<[index: number, gain: number, scope: Scope, appid: string | null], AudioState>("set_audio_band");
export const setAudioBands =
  callable<[gains: number[], scope: Scope, appid: string | null], AudioState>("set_audio_bands");
export const setAudioFollowGlobal =
  callable<[follow: boolean, appid: string | null], AudioState>("set_audio_follow_global");
export const resetAudio =
  callable<[scope: Scope, appid: string | null], AudioState>("reset_audio");
export const setAudioCurve =
  callable<[gains: number[], bass: number, scope: Scope, appid: string | null], AudioState>("set_audio_curve");
export const setAudioLoudness =
  callable<[on: boolean, scope: Scope, appid: string | null], AudioState>("set_audio_loudness");
export const setAudioTest =
  callable<[playing: boolean, sample: string], AudioState>("set_audio_test");
export const saveAudioProfile = callable<[name: string], AudioState>("save_audio_profile");
export const applyAudioProfile =
  callable<[name: string, scope: Scope, appid: string | null], AudioState>("apply_audio_profile");
export const deleteAudioProfile = callable<[name: string], AudioState>("delete_audio_profile");
