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
