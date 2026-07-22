// Pure module enable/disable logic (cascade + dependency). No React, no storage.
// Mirrors the Python _module_enabled so front and back agree.

export type ModuleId =
  | "power" | "system" | "display" | "fans" | "mandos"
  | "autoTdp" | "fanControl" | "learning";

interface Requirement {
  mode: "all" | "any";
  ids: ModuleId[];
}

// Section tabs backed by a backend module (disable-able); others are hide-only.
const SECTION_MODULES = new Set<string>(["power", "system", "display", "fans", "mandos"]);
export const isDisableableSection = (id: string): boolean => SECTION_MODULES.has(id);

// autoTdp/fanControl cascade from their tab (all); learning needs a consumer (any).
export const REQUIRES: Partial<Record<ModuleId, Requirement>> = {
  autoTdp: { mode: "all", ids: ["power"] },
  fanControl: { mode: "all", ids: ["fans"] },
  learning: { mode: "any", ids: ["power", "fans"] },
};

/** Effective state: not user-disabled AND its requirements hold. */
export function effectiveEnabled(id: string, disabled: Set<string>): boolean {
  if (disabled.has(id)) return false;
  const req = REQUIRES[id as ModuleId];
  if (!req) return true;
  const deps = req.ids.map((d) => effectiveEnabled(d, disabled));
  return req.mode === "any" ? deps.some(Boolean) : deps.every(Boolean);
}

export type ModuleState = "visible" | "background" | "disabled" | "blocked" | "locked";

/** UI state for one module row. `blocked` = not user-disabled but a dependency is
 *  unmet (e.g. learning with Power+Fans off) → the switch is inert with a reason. */
export function moduleState(
  id: string,
  disabled: Set<string>,
  hidden: boolean,
  pinned: boolean,
): ModuleState {
  if (pinned) return "locked";
  if (disabled.has(id)) return "disabled";
  if (!effectiveEnabled(id, disabled)) return "blocked";
  return hidden ? "background" : "visible";
}

/** Summary counts for the editor header chip (blocked folded with disabled by callers). */
export function countStates(
  items: { id: string; hidden: boolean }[],
  disabled: Set<string>,
): { visible: number; background: number; disabled: number; blocked: number } {
  const out = { visible: 0, background: 0, disabled: 0, blocked: 0 };
  for (const { id, hidden } of items) {
    const s = moduleState(id, disabled, hidden, false);
    if (s === "visible") out.visible++;
    else if (s === "background") out.background++;
    else if (s === "disabled") out.disabled++;
    else if (s === "blocked") out.blocked++;
  }
  return out;
}
