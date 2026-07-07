export type ScalarKind = "brightness" | "volume";

const lastWrite: Record<ScalarKind, number | null> = { brightness: null, volume: null };

export function markSelfWrite(kind: ScalarKind): void {
  lastWrite[kind] = Date.now();
}

export function lastSelfWrite(kind: ScalarKind): number | null {
  return lastWrite[kind];
}
