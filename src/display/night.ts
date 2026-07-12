// Pure helpers for the night-mode time controls. Times are minutes-of-day (0..1439).
const DAY = 24 * 60;

/** Format a minute-of-day as "HH:MM" (24h, zero-padded). */
export function toHHMM(min: number): string {
  const h = Math.floor(min / 60) % 24;
  const m = ((min % 60) + 60) % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** Step a minute-of-day by `steps * size` minutes, wrapping around the day. Used by
 *  the hour (size 60) and minute (size 15) steppers. */
export function stepMinutes(min: number, steps: number, size: number): number {
  return (((min + steps * size) % DAY) + DAY) % DAY;
}
