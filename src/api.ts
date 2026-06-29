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
}

export interface TdpApplyResult {
  requested_w: number;
  applied_w: number | null;
  ok: boolean;
  detail: string;
}

export type TdpScope = "global" | "game";

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
export const resetTdpAuto = callable<[scope: TdpScope, appid: string | null], TdpApplyResult>("reset_tdp_auto");

export interface PowerDraw {
  watts: number | null;
  gpu_busy: number | null;
  auto_tdp: boolean;
  setpoint: number | null;
}

export const getPowerDraw = callable<[], PowerDraw>("get_power_draw");
export const setAutoTdp = callable<[enabled: boolean], { auto_tdp: boolean }>("set_auto_tdp");
