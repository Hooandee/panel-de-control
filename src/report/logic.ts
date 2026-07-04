// Pure logic for the bug-report modal. Kept free of @decky/ui imports so it stays
// unit-testable (importing @decky/ui in a tested module breaks vitest - no window).

// Category ids the backend + collector understand. Labels are i18n `report.cat.<id>`.
export const REPORT_CATEGORIES = [
  "tdp",
  "fans",
  "display",
  "controllers",
  "battery",
  "system",
  "other",
] as const;

export type ReportCategory = (typeof REPORT_CATEGORIES)[number];

/** Toggle a category in the selection (add if absent, remove if present). */
export function toggleCategory(
  selected: ReportCategory[],
  id: ReportCategory,
): ReportCategory[] {
  return selected.includes(id)
    ? selected.filter((x) => x !== id)
    : [...selected, id];
}

/** A report is sendable once the user has marked at least one category OR written
 *  something - an empty report helps nobody. */
export function canSubmit(selected: ReportCategory[], text: string): boolean {
  return selected.length > 0 || text.trim().length > 0;
}
