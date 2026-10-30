import type { Channel } from "./types";

const TOP_GROUPS = 14;

/** Most common groups first: long IPTV lists carry hundreds, only the big ones earn a chip. */
export function topGroups(channels: readonly Channel[], limit = TOP_GROUPS): string[] {
  const counts = new Map<string, number>();
  for (const channel of channels) if (channel.group) counts.set(channel.group, (counts.get(channel.group) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, limit).map(([group]) => group);
}

export function filterChannels(channels: readonly Channel[], query: string, group: string | null): Channel[] {
  const needle = query.trim().toLowerCase();
  return channels.filter((c) => (!group || c.group === group) && (!needle || c.name.toLowerCase().includes(needle)));
}
