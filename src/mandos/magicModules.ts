import type {
  ControllerAction,
  ControllerActionOutcome,
  MagicModuleState,
  MagicModulesState,
} from "../api";

const ACTION_TARGETS: Record<ControllerAction, ("left" | "right")[]> = {
  eject_left: ["left"],
  eject_right: ["right"],
  eject_both: ["left", "right"],
};

export function canEject(
  modules: MagicModulesState,
  action: ControllerAction,
  pending: ControllerAction | null,
): boolean {
  if (!modules.supported || modules.busy || pending !== null) return false;
  return ACTION_TARGETS[action].every((side) => modules[side] === "connected");
}

export function moduleStateKey(state: MagicModuleState): string {
  return `mandos.modules.state.${state}`;
}

export function outcomeKey(outcome: ControllerActionOutcome): string {
  return `mandos.modules.result.${outcome}`;
}
