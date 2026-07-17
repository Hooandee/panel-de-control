// Hidden-games list for the Parámetros section. The set of game stableKeys the
// user has hidden, persisted durably (pdc: key → backend-mirrored). Pure parser.

export const HIDDEN_KEY = "pdc:launchHidden";

/** Parse the stored JSON array of stable keys. Never throws; drops non-strings,
 *  dedupes, and returns [] for anything that isn't a string array. */
export function parseHidden(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    if (!Array.isArray(v)) return [];
    return [...new Set(v.filter((x): x is string => typeof x === "string"))];
  } catch {
    return [];
  }
}
