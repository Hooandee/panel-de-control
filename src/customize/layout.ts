// Pure layout logic for the customization feature (tab + block reordering and
// hiding). No React, no localStorage here — the store owns persistence, the
// editor owns the UI. Kept pure so the forward/backward-compat rules are
// unit-testable.

/** Order + visibility preference for one list (the tabs, or one section's blocks). */
export interface ListPref {
  /** Explicit id order. Ids not in `defaults` are ignored; missing defaults append. */
  order: string[];
  /** Ids the user chose to hide. */
  hidden: string[];
}

/** The whole saved layout: tab prefs + per-section block prefs. */
export interface Layout {
  tabs: ListPref;
  blocks: Record<string, ListPref>;
  /**
   * Hidden sub-item ids per block (keyed by block id). Sub-items are a fixed
   * part of their block — they can only be hidden, not reordered — so this is a
   * plain hidden-id list, not a full ListPref.
   */
  subitems: Record<string, string[]>;
}

/**
 * Resolve the full ordered id list from a stored order against the current
 * defaults. Tolerant by design: stale ids (dropped from the code) disappear,
 * and NEW defaults the saved pref never saw get appended at the end (visible)
 * so a future release that adds a block/tab never loses or hides it.
 */
export function orderIds(defaults: string[], order: string[] | undefined): string[] {
  const known = new Set(defaults);
  const seen = new Set<string>();
  const result: string[] = [];
  for (const id of order ?? []) {
    if (known.has(id) && !seen.has(id)) {
      result.push(id);
      seen.add(id);
    }
  }
  for (const id of defaults) {
    if (!seen.has(id)) result.push(id);
  }
  return result;
}

/**
 * The ids to actually render: ordered, minus hidden ones. `pinned` ids stay
 * visible even if the pref marks them hidden (the escape-hatch tab).
 */
export function visibleIds(
  defaults: string[],
  pref: ListPref | undefined,
  pinned: string[] = [],
): string[] {
  const hidden = new Set(pref?.hidden ?? []);
  const pin = new Set(pinned);
  return orderIds(defaults, pref?.order).filter((id) => pin.has(id) || !hidden.has(id));
}

/** Immutably swap `id` one step up (dir -1) or down (dir +1). No-op at edges. */
export function move(list: string[], id: string, dir: -1 | 1): string[] {
  const i = list.indexOf(id);
  if (i < 0) return list;
  const j = i + dir;
  if (j < 0 || j >= list.length) return list;
  const copy = list.slice();
  [copy[i], copy[j]] = [copy[j], copy[i]];
  return copy;
}

/** Immutably add `id` if absent, remove it if present. */
export function toggle(set: string[], id: string): string[] {
  return set.includes(id) ? set.filter((x) => x !== id) : [...set, id];
}

/** Whether a fixed sub-item within a block is hidden by the user's prefs. */
export function subitemHidden(
  subitems: Record<string, string[]>,
  group: string,
  id: string,
): boolean {
  return (subitems[group] ?? []).includes(id);
}

export const strArray = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];

const asPref = (v: unknown): ListPref => {
  const o = (v && typeof v === "object" ? v : {}) as { order?: unknown; hidden?: unknown };
  return { order: strArray(o.order), hidden: strArray(o.hidden) };
};

/**
 * Coerce arbitrary parsed JSON into a valid Layout. localStorage can hold a
 * corrupt or old-shape value (valid JSON but wrong types, e.g. `order: 5`);
 * without this, `for..of` / `new Set` on a non-array throws during render and,
 * caught by the top-level ErrorBoundary with no in-UI recovery, permanently
 * bricks the panel. Everything unrecognized degrades to the empty layout.
 */
export function coerceLayout(parsed: unknown): Layout {
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { tabs: { order: [], hidden: [] }, blocks: {}, subitems: {} };
  }
  const p = parsed as { tabs?: unknown; blocks?: unknown; subitems?: unknown };
  const asRecordOf = <T>(v: unknown, mapVal: (x: unknown) => T): Record<string, T> => {
    const out: Record<string, T> = {};
    if (v && typeof v === "object" && !Array.isArray(v)) {
      for (const [k, val] of Object.entries(v)) out[k] = mapVal(val);
    }
    return out;
  };
  return {
    tabs: asPref(p.tabs),
    blocks: asRecordOf(p.blocks, asPref),
    subitems: asRecordOf(p.subitems, strArray),
  };
}
