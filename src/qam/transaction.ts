export type QamEntryTransactionResult =
  | { applied: true }
  | { applied: false; reason: "readback_mismatch" | "readback_threw" };

function replace<T>(target: T[], entries: readonly T[]): void {
  target.splice(0, target.length, ...entries);
}

function matches<T>(target: readonly T[], expected: readonly T[]): boolean {
  return target.length === expected.length
    && target.every((entry, index) => entry === expected[index]);
}

export function applyQamEntryTransaction<T>(
  target: T[],
  desired: readonly T[],
  verify: () => boolean,
): QamEntryTransactionResult {
  const previous = [...target];
  replace(target, desired);
  try {
    if (verify() && matches(target, desired)) return { applied: true };
    replace(target, previous);
    return { applied: false, reason: "readback_mismatch" };
  } catch {
    replace(target, previous);
    return { applied: false, reason: "readback_threw" };
  }
}
