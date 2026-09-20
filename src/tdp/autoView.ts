import { AutoTdpConfig, PowerDraw, TdpLimits, TdpScope } from "../api";

interface AutoScopeState {
  follows_global: boolean;
  auto_config: AutoTdpConfig;
  global_auto_config: AutoTdpConfig;
  auto_limits: TdpLimits;
  auto_request_limits: TdpLimits;
  on_ac: boolean;
}

export function effectiveAutoRange(config: AutoTdpConfig, limits: TdpLimits, onAc: boolean): { min: number; max: number } {
  const maximum = onAc ? limits.max_ac : limits.max;
  return {
    min: Math.max(limits.min, Math.min(config.min_tdp ?? limits.min, maximum)),
    max: Math.max(limits.min, Math.min(config.max_tdp ?? maximum, maximum)),
  };
}

export function resolveAutoView(
  tdp: AutoScopeState,
  power: PowerDraw | null,
  scope: TdpScope,
  hasGame: boolean,
): {
  config: AutoTdpConfig;
  liveApplies: boolean;
  hideManualSuggestion: boolean;
  power: PowerDraw | null;
} {
  const config = scope === "global" ? tdp.global_auto_config : tdp.auto_config;
  const liveApplies = Boolean(
    hasGame && (scope === "game" || tdp.follows_global),
  );
  const hideManualSuggestion = hasGame && Boolean(power?.auto_tdp);
  if (!power) return { config, liveApplies, hideManualSuggestion, power: null };
  let setpoint = power.setpoint;
  if (config.enabled) {
    if (liveApplies) {
      setpoint = power.auto?.held_watts ?? power.setpoint;
    } else if (hasGame) {
      setpoint = config.initial_tdp;
    } else {
      const range = effectiveAutoRange(config, tdp.auto_limits, tdp.on_ac);
      setpoint = Math.max(range.min, Math.min(tdp.auto_request_limits.default, range.max));
    }
  }
  return {
    config,
    liveApplies,
    hideManualSuggestion,
    power: {
      ...power,
      auto_tdp: config.enabled,
      setpoint,
    },
  };
}
