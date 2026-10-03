// How often shared hooks poll the backend, as a multiple of their QAM cadence. The QAM is read up
// close and briefly; the bottom screen is glanced at for hours while a game runs, so it polls slower.
let factor = 1;

export function setPollFactor(next: number): void {
  factor = Math.max(1, next);
}

export const pollMs = (ms: number): number => ms * factor;
