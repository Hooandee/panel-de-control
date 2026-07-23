// Pure resolution of the power-preset library into UI item lists. No React, no RPC.
// Built-in watts come from the live TdpState.presets (AC-aware) — never cached here.
import type { PowerPresetState, PowerPresetBoost } from "../api";

export const BUILTIN_IDS = ["quiet", "balanced", "turbo"] as const;
export type BuiltinId = (typeof BUILTIN_IDS)[number];

const BUILTIN_ICON: Record<BuiltinId, string> = {
  quiet: "leaf",
  balanced: "gauge",
  turbo: "rocket",
};

export interface BuiltinWatts {
  quiet: number;
  balanced: number;
  turbo: number;
  turbo_ac: number;
}

export interface PresetItem {
  id: string;
  kind: "builtin" | "custom";
  watts: number;
  label: string; // "12W"
  icon: string;
  boost: PowerPresetBoost | null;
  hidden: boolean;
  active: boolean; // matches current watts
  editable: boolean; // custom only
  deletable: boolean; // custom only
}

export interface ResolvedPresets {
  visible: PresetItem[]; // ordered, not hidden — for the chip row
  manager: PresetItem[]; // ordered, ALL (incl. hidden) — for the modal
  allHidden: boolean;
}

const isBuiltin = (id: string): id is BuiltinId =>
  (BUILTIN_IDS as readonly string[]).includes(id);

function builtinWattsFor(id: BuiltinId, w: BuiltinWatts, onAc: boolean): number {
  if (id === "turbo") return onAc ? w.turbo_ac : w.turbo;
  return w[id];
}

export function resolveItems(
  state: PowerPresetState,
  watts: BuiltinWatts,
  onAc: boolean,
  currentWatts: number,
): ResolvedPresets {
  const hidden = new Set(state.hidden);
  const cur = Math.round(currentWatts);
  const manager: PresetItem[] = [];
  for (const id of state.order) {
    let item: PresetItem | null = null;
    if (isBuiltin(id)) {
      const w = builtinWattsFor(id, watts, onAc);
      item = {
        id,
        kind: "builtin",
        watts: w,
        label: `${w}W`,
        icon: BUILTIN_ICON[id],
        boost: null,
        hidden: hidden.has(id),
        active: Math.round(w) === cur,
        editable: false,
        deletable: false,
      };
    } else {
      const c = state.custom[id];
      if (c) {
        item = {
          id,
          kind: "custom",
          watts: c.watts,
          label: `${c.watts}W`,
          icon: c.icon,
          boost: c.boost,
          hidden: hidden.has(id),
          active: Math.round(c.watts) === cur,
          editable: true,
          deletable: true,
        };
      }
    }
    if (item) manager.push(item);
  }
  const visible = manager.filter((i) => !i.hidden);
  return {
    visible,
    manager,
    allHidden: manager.length > 0 && visible.length === 0,
  };
}
