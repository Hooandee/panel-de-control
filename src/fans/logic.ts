// Pure helpers for the fan monitor: a rolling sample buffer and an SVG sparkline
// path. Kept pure so they're unit-testable; components consume them.

/** Append `value`, keeping at most `max` most-recent samples. Returns a new array. */
export function pushSample(buffer: number[], value: number, max: number): number[] {
  const next = [...buffer, value];
  return next.length > max ? next.slice(next.length - max) : next;
}

/**
 * SVG path for a sparkline over `values`, fitted to `width`×`height`. The max
 * value sits at the top (y=0), the min at the bottom (y=height); all-equal
 * values draw a flat mid line. Empty input → "".
 */
export function sparklinePath(values: number[], width: number, height: number): string {
  const n = values.length;
  if (n === 0) return "";

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;

  const x = (i: number) => (n === 1 ? 0 : Math.round((i / (n - 1)) * width));
  const y = (v: number) =>
    span === 0 ? Math.round(height / 2) : Math.round(height - ((v - min) / span) * height);

  return values
    .map((v, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(v)}`)
    .join(" ");
}
