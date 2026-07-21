// Game-list ordering for the Parámetros section.

export type SortMode = "recent" | "alpha" | "played";

type Sortable = { name: string; lastPlayed: number; playtime: number };

const byName = (a: Sortable, b: Sortable) => a.name.localeCompare(b.name);

/** Return a new array sorted by the chosen mode. "recent" mirrors Steam's grid:
 *  most-recently-played first, never-played (lastPlayed 0) last, ties by name. */
export function sortGames<T extends Sortable>(games: T[], mode: SortMode): T[] {
  const out = [...games];
  if (mode === "alpha") {
    out.sort(byName);
  } else if (mode === "played") {
    out.sort((a, b) => b.playtime - a.playtime || byName(a, b));
  } else {
    out.sort((a, b) => b.lastPlayed - a.lastPlayed || byName(a, b));
  }
  return out;
}
