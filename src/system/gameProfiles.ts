import type { GameProfileRow } from "../api";

const SECTIONS = ["tdp", "fan", "color", "cpu", "mandos", "audio"] as const;
export type SectionId = (typeof SECTIONS)[number];

/** The section ids that have a stored profile in this row, in display order. */
export function configuredSections(row: GameProfileRow): SectionId[] {
  return SECTIONS.filter((s) => row[s] !== undefined);
}
