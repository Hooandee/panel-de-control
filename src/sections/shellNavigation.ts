import type { ShellMode } from "./shellMode";

export interface ShellState {
  mode: ShellMode;
  activeId: string | null;
}

export function resolveShellState(
  storedMode: ShellMode | null,
  activeId: string | null,
  visibleIds: readonly string[],
  showHome: boolean,
): ShellState {
  const validActive = activeId !== null && visibleIds.includes(activeId);
  const resolvedActive = validActive ? activeId : visibleIds[0] ?? null;

  if (!showHome) return { mode: "tabs", activeId: resolvedActive };
  if (storedMode === null) return { mode: "home", activeId: resolvedActive };
  if (storedMode === "home") return { mode: "home", activeId: resolvedActive };
  if (!validActive) return { mode: "home", activeId: resolvedActive };
  return { mode: storedMode, activeId: resolvedActive };
}
