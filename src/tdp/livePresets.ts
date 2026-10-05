import type { PowerPresetState, TdpScope, TdpState } from "../api";
import { offsetOf } from "./logic";
import { BUILTIN_IDS, resolveItems, ResolvedPresets } from "./powerPresets";
import { isLevelUnit } from "./unit";

/** The preset library resolved against the live power state of a scope (QAM and bottom screen). */
export function resolveLivePresets(
  tdp: TdpState,
  presets: PowerPresetState | null,
  scope: TdpScope,
  t: (key: string, vars?: Record<string, string | number>) => string,
): ResolvedPresets {
  const lib = presets ?? { order: [...BUILTIN_IDS], hidden: [], custom: {} };
  const ceiling = tdp.on_ac ? tdp.limits.max_ac : tdp.limits.max;
  const w = scope === "global" ? tdp.global_watts : tdp.watts;
  const lv = scope === "global"
    ? (tdp.global_requested_levels ?? tdp.global_levels)
    : (tdp.requested_levels ?? tdp.levels);
  const mode = scope === "global" ? tdp.global_boost_mode : tdp.boost_mode;
  const liveBoost = { mode, off2: offsetOf(lv.pl2, lv.pl1), off3: offsetOf(lv.pl3, lv.pl2) };
  return resolveItems(
    lib, tdp.presets, tdp.on_ac, w, ceiling, liveBoost,
    isLevelUnit(tdp.unit) ? (level) => t("tdp.level.value", { level }) : undefined,
  );
}
