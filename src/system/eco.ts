// Pure helpers for download mode's ambient dim.

export function ecoBrightness(active: boolean, wakePct: number, floorPct: number): number {
  return active ? wakePct : floorPct;
}

// True when a brightness echo is our own recent write, not a user change.
export function isDimEcho(
  echo: number,
  lastDriven: number | null,
  msSinceDrive: number,
  windowMs = 2000,
  tol = 2,
): boolean {
  if (lastDriven === null) return false;
  return Math.abs(echo - lastDriven) <= tol && msSinceDrive <= windowMs;
}

// A change at the idle floor is our dim, never a wake level to adopt.
export function isFloorEcho(echo: number, floorPct: number, tol = 2): boolean {
  return Math.abs(echo - floorPct) <= tol;
}

// Wake fast, hold on idle so activity flapping doesn't flicker the screen.
export function activityDebounceMs(active: boolean): number {
  return active ? 150 : 800;
}
