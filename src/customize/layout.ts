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

const strArray = (v: unknown): string[] =>
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
    return { tabs: { order: [], hidden: [] }, blocks: {} };
  }
  const p = parsed as { tabs?: unknown; blocks?: unknown };
  const blocks: Record<string, ListPref> = {};
  if (p.blocks && typeof p.blocks === "object" && !Array.isArray(p.blocks)) {
    for (const [k, v] of Object.entries(p.blocks)) blocks[k] = asPref(v);
  }
  return { tabs: asPref(p.tabs), blocks };
}
