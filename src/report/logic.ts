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
  "launch",
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

/** A report is sendable once the user has written something. Without a description
 *  a report is almost impossible to act on, so the text is required; categories
 *  alone are not enough. */
export function canSubmit(_selected: ReportCategory[], text: string): boolean {
  return text.trim().length > 0;
}
