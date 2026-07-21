// Hidden-games list for the Parámetros section. The exact library-entry keys the
// user has hidden, persisted durably (pdc: key → backend-mirrored). Pure parser.

export const HIDDEN_KEY = "pdc:launchHidden";

/** Parse the stored JSON array of entry keys. Never throws; drops non-strings,
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

export async function commitHiddenChange(
  previous: string[],
  next: string[],
  persist: (value: string) => Promise<boolean>,
): Promise<{ value: string[]; saved: boolean }> {
  try {
    if (await persist(JSON.stringify(next))) return { value: next, saved: true };
  } catch {
    /* handled by the caller's rollback */
  }
  return { value: previous, saved: false };
}
