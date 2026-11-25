import type { GamePowerOwnerState } from "../api";

const listeners = new Set<(owner: GamePowerOwnerState) => void>();

export function subscribePowerOwnershipChanged(listener: (owner: GamePowerOwnerState) => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function notifyPowerOwnershipChanged(owner: GamePowerOwnerState): void {
  for (const listener of listeners) listener(owner);
}
