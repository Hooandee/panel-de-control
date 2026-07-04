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

/**
 * Fan speed as a 0..1 fraction for the gauge ring. The hardware doesn't expose
 * PWM duty on every device, but RPM is real — so we show RPM relative to a max.
 * The denominator self-calibrates to the fastest speed seen this session
 * (`observedMax`) but never drops below `nominalMax`, so the ring is meaningful
 * immediately and never overclaims (a fan at its session peak reads ~full).
 */
export function rpmFraction(rpm: number, observedMax: number, nominalMax: number): number {
  const denom = Math.max(nominalMax, observedMax);
  if (denom <= 0) return 0;
  return Math.max(0, Math.min(1, rpm / denom));
}

// The fixed presets that share a near-flat, quiet low-temp region. Below this
// temperature their curves overlap and the fan sits at its hardware floor, so
// switching between them makes no audible/RPM difference — they only diverge
// under load: at low temps silent/balanced/performance all hold the same floor
// RPM; only at high temps do they diverge.
const _FIXED_PRESETS = ["silent", "balanced", "performance"] as const;
const _DIVERGENCE_TEMP_C = 60;

/**
 * Whether a fixed fan preset is active but the device is still cool enough that
 * all presets look identical (fan at its floor). Used to show an honest hint so
 * the user doesn't read idle-convergence as "the preset didn't apply". Only the
 * three fixed presets qualify; auto/custom/adaptive never do. A null live temp
 * (no marker) → false.
 */
export function presetConverges(preset: string, liveTemp: number | null): boolean {
  if (liveTemp === null) return false;
  if (!(_FIXED_PRESETS as readonly string[]).includes(preset)) return false;
  return liveTemp < _DIVERGENCE_TEMP_C;
}
