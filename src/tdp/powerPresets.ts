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

/** Comparable signature of a boost config; custom includes its margins. */
function boostKey(b: PowerPresetBoost): string {
  return b.mode === "custom" ? `custom:${b.off2}:${b.off3}` : b.mode;
}

export function resolveItems(
  state: PowerPresetState,
  watts: BuiltinWatts,
  onAc: boolean,
  currentWatts: number,
  activeMax: number,
  liveBoost: PowerPresetBoost,
): ResolvedPresets {
  const hidden = new Set(state.hidden);
  const cur = Math.round(currentWatts);
  const liveKey = boostKey(liveBoost);
  // Build the rows first with a watts-match flag; active is resolved in a second pass
  // because a watts-only preset is only active when NO fuller (watts+boost) preset
  // reproduces the live state — otherwise two same-watt presets would both light.
  const rows: (PresetItem & { wm: boolean })[] = [];
  for (const id of state.order) {
    if (isBuiltin(id)) {
      const w = builtinWattsFor(id, watts, onAc);
      rows.push({
        id, kind: "builtin", watts: w, label: `${w}W`, icon: BUILTIN_ICON[id], boost: null,
        hidden: hidden.has(id), active: false, editable: false, deletable: false,
        wm: Math.round(w) === cur,
      });
    } else {
      const c = state.custom[id];
      if (c) {
        // Clamp the shown/active watts to what the current power source can deliver, so a
        // charger-created preset doesn't advertise unreachable watts on battery (apply
        // re-clamps server-side too, keeping the active highlight honest).
        const w = Math.min(c.watts, activeMax);
        rows.push({
          id, kind: "custom", watts: w, label: `${w}W`, icon: c.icon, boost: c.boost,
          hidden: hidden.has(id), active: false, editable: true, deletable: true,
          wm: Math.round(w) === cur,
        });
      }
    }
  }
  const isFull = (r: (typeof rows)[number]) => r.wm && r.boost != null && boostKey(r.boost) === liveKey;
  const anyFull = rows.some(isFull);
  const manager: PresetItem[] = rows.map(({ wm, ...item }) => ({
    ...item,
    // Boosted preset: active on an exact watts+boost match. Watts-only preset (incl.
    // builtins): active on a watts match only when nothing fuller matches the live state.
    active: isFull({ ...item, wm }) || (item.boost == null && wm && !anyFull),
  }));
  const visible = manager.filter((i) => !i.hidden);
  return {
    visible,
    manager,
    allHidden: manager.length > 0 && visible.length === 0,
  };
}
