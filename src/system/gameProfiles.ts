import type { GameProfileRow } from "../api";

const SECTIONS = ["tdp", "fan", "color", "cpu", "mandos"] as const;
export type SectionId = (typeof SECTIONS)[number];

/** A non-Steam shortcut is keyed "ns:<normalized name>" (see tdp/gameIdentity). */
export function isNonSteamKey(appid: string): boolean {
  return appid.startsWith("ns:");
}

/** The stored (normalized) name of a non-Steam shortcut, from its key. */
export function nonSteamName(appid: string): string {
  return appid.slice(3);
}

/** The section ids that have a stored profile in this row, in display order. */
export function configuredSections(row: GameProfileRow): SectionId[] {
  return SECTIONS.filter((s) => row[s] !== undefined);
}
