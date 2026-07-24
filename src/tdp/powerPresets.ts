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

// i18n keys for the built-in preset names (resolved by the component, kept here so the
// modal and the chip row agree on the mapping).
export const BUILTIN_LABEL_KEY: Record<string, string> = {
  quiet: "tdp.preset.save",
  balanced: "tdp.preset.balanced",
  turbo: "tdp.preset.turbo",
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
  name: string; // custom user name ("" if none); builtin names come from BUILTIN_LABEL_KEY
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

// Shared label logic for the chip row and the manager row (kept together so they can't
// drift). Title = builtin name (via i18n) or the custom name, falling back to the watts;
// the watts read as a secondary line whenever the title isn't already the watts.
export function presetTitle(it: PresetItem, t: (key: string) => string): string {
  return it.kind === "builtin" ? t(BUILTIN_LABEL_KEY[it.id]) : it.name || it.label;
}
export function presetSub(it: PresetItem): string {
  return it.kind === "builtin" || it.name ? it.label : "";
}

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
        id, kind: "builtin", watts: w, label: `${w}W`, name: "", icon: BUILTIN_ICON[id], boost: null,
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
          id, kind: "custom", watts: w, label: `${w}W`, name: c.name ?? "", icon: c.icon, boost: c.boost,
          hidden: hidden.has(id), active: false, editable: true, deletable: true,
          wm: Math.round(w) === cur,
        });
      }
    }
  }
  // A preset with a defined boost (estable/auto/custom) is a "full" match only when its
  // exact boost equals the live boost — estable included, since it forces flat rails, which
  // differs from live auto/custom. A boost=null preset (builtins: leave-untouched) matches
  // on watts alone, but only when nothing fuller reproduces the live state.
  const isFull = (r: (typeof rows)[number]) => r.wm && r.boost != null && boostKey(r.boost) === liveKey;
  const anyFull = rows.some(isFull);
  // Only the FIRST full match lights, so two identical presets can't both read as active
  // (you'd never know which is applied). Watts-only builtins still light together — they're
  // interchangeable, so it doesn't matter which.
  let fullClaimed = false;
  const manager: PresetItem[] = rows.map((r) => {
    const { wm, ...item } = r;
    let active = false;
    if (isFull(r)) {
      active = !fullClaimed;
      fullClaimed = true;
    } else if (r.boost == null && wm && !anyFull) {
      active = true;
    }
    return { ...item, active };
  });
  const visible = manager.filter((i) => !i.hidden);
  return {
    visible,
    manager,
    allHidden: manager.length > 0 && visible.length === 0,
  };
}
