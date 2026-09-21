import type { CleanerEntry } from "./types";

export interface CleanerMetadata { name: string; coverUrls: string[] }
export interface CleanerGame extends CleanerMetadata { id: string; entries: CleanerEntry[]; bytes: number; sizeUnknown: boolean }
export type CleanerFilter = "all" | "cleanable" | "not_installed" | "selected";
export type CleanerSort = "size" | "name";

export function groupEntries(entries: CleanerEntry[], metadata: ReadonlyMap<string, CleanerMetadata>): CleanerGame[] {
  const groups = new Map<string, CleanerGame>();
  for (const entry of entries) {
    let group = groups.get(entry.game_id);
    if (!group) {
      const visual = metadata.get(entry.appid);
      group = { id: entry.game_id, name: entry.name || visual?.name || "", coverUrls: visual?.coverUrls ?? [], entries: [], bytes: 0, sizeUnknown: false };
      groups.set(entry.game_id, group);
    }
    group.entries.push(entry);
    group.bytes += entry.bytes ?? 0;
    group.sizeUnknown ||= entry.bytes === null;
  }
  return [...groups.values()];
}

export function filterGames(games: CleanerGame[], query: string, filter: CleanerFilter, sort: CleanerSort, selected: ReadonlySet<string>): CleanerGame[] {
  const needle = query.trim().toLocaleLowerCase();
  return games.filter((game) =>
    (!needle || game.name.toLocaleLowerCase().includes(needle) || game.entries.some((entry) => entry.appid.includes(needle)))
    && (filter !== "cleanable" || game.entries.some((entry) => !entry.blocked_reason))
    && (filter !== "not_installed" || game.entries.some((entry) => entry.installation === "not_installed"))
    && (filter !== "selected" || game.entries.some((entry) => selected.has(entry.id))))
    .sort((a, b) => (sort === "size" ? b.bytes - a.bytes : 0) || a.name.localeCompare(b.name));
}

export function eligibleCaches(entries: CleanerEntry[]): CleanerEntry[] {
  return entries.filter((entry) => entry.kind === "shadercache" && !entry.blocked_reason && !entry.requires_manual_selection);
}

export function toggleCaches(entries: CleanerEntry[], selected: ReadonlySet<string>): Set<string> {
  const caches = eligibleCaches(entries);
  const remove = caches.length > 0 && caches.every((entry) => selected.has(entry.id));
  const next = new Set(selected);
  for (const entry of caches) {
    if (remove) next.delete(entry.id);
    else next.add(entry.id);
  }
  return next;
}

export function toggleEntry(entry: CleanerEntry, selected: ReadonlySet<string>): Set<string> {
  const next = new Set(selected);
  if (entry.blocked_reason) return next;
  if (next.has(entry.id)) next.delete(entry.id);
  else next.add(entry.id);
  return next;
}

export function formatBytes(bytes: number, locale: string): string {
  const unit = bytes >= 1e9 ? "GB" : bytes >= 1e6 ? "MB" : bytes >= 1e3 ? "KB" : "B";
  const divisor = { B: 1, KB: 1e3, MB: 1e6, GB: 1e9 }[unit];
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: unit === "B" ? 0 : 1 }).format(bytes / divisor)} ${unit}`;
}
