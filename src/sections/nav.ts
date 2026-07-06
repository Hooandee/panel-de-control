// Navigation logic for the control-center shell. Kept pure (no React) so the
// active-section resolution is unit-testable and the navigator (TabBar today,
// possibly a dropdown later) stays a thin presentation layer over this.

/**
 * Picks the section to render for the given active id. Falls back to the first
 * section when the id is unknown (e.g. a stale id after the registry changes),
 * and returns undefined only when there are no sections at all.
 */
export function resolveActiveSection<T extends { id: string }>(
  sections: T[],
  activeId: string,
): T | undefined {
  return sections.find((s) => s.id === activeId) ?? sections[0];
}

/**
 * Next (dir +1) or previous (dir -1) tab id, wrapping around the ends — the
 * shoulder buttons (L1/R1) cycle the tab bar. Returns the active id unchanged
 * when it isn't in the list or there's nothing to cycle.
 */
export function cycleTab(ids: string[], activeId: string, dir: -1 | 1): string {
  const i = ids.indexOf(activeId);
  if (i < 0 || ids.length === 0) return activeId;
  const n = ids.length;
  return ids[(i + dir + n) % n];
}
