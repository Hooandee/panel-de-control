import type { TdpState } from "../../../src/api";

export function stepRange(tdp: TdpState | null, onAc: boolean): { min: number; max: number } {
  if (!tdp?.limits) return { min: 0, max: 1 };
  const max = onAc ? Math.max(tdp.limits.max, tdp.limits.max_ac) : tdp.limits.max;
  return { min: tdp.limits.min, max: Math.max(tdp.limits.min + 1, max) };
}

export const clamp01 = (value: number): number => Math.max(0, Math.min(1, value));

/** Whole step under a finger `offset` px into a track of `size` px, with `pad` px of dead edge each side. */
export function stepAt(offset: number, size: number, pad: number, min: number, max: number): number {
  const span = size - 2 * pad;
  const fraction = span > 0 ? clamp01((offset - pad) / span) : 0;
  return Math.round(min + fraction * (max - min));
}

export function levelCaption(tdp: TdpState | null, level: number | null, lang: string): string {
  const freq = level != null ? tdp?.level_frequencies?.[String(level)] : undefined;
  if (!freq) return "";
  const ghz = Math.max(...freq.cpu_khz) / 1e6;
  const cpu = ghz.toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return `${cpu} GHz · ${freq.gpu_mhz} MHz`;
}

export function pushSample(samples: readonly number[], value: number, keep: number): number[] {
  return [...samples, value].slice(-keep);
}

/** Frame-pacing line: dips read as drops below the dashed target line near the top. */
export function pacePath(
  samples: readonly number[],
  target: number | null,
  width: number,
  height: number,
): { line: string; targetY: number | null } {
  const ceiling = Math.max(target ?? 0, ...samples, 1) * 1.08;
  const y = (v: number) => (height - (v / ceiling) * height).toFixed(1);
  const targetY = target != null ? Number(y(target)) : null;
  if (samples.length < 2) return { line: "", targetY };
  const step = width / (samples.length - 1);
  const line = samples.map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${y(v)}`).join(" ");
  return { line, targetY };
}

export function formatPlaying(seconds: number | null): string | null {
  if (seconds == null || seconds < 60) return null;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

const FPS_TARGETS = [30, 40, 45, 60, 90, 120, 144];
const MAX_FPS_ORBS = 5;
const MIN_TARGET_FPS = 20;

/** Common frame-rate targets the device can actually reach, highest kept when trimming. */
export function fpsChoices(maxFps: number | null | undefined): number[] {
  const ceiling = Math.max(MIN_TARGET_FPS, maxFps ?? 60);
  const reachable = FPS_TARGETS.filter((fps) => fps <= ceiling);
  if (reachable.length <= MAX_FPS_ORBS) return reachable;
  return reachable.filter((fps) => fps !== 45).slice(-MAX_FPS_ORBS);
}

const COMMON_RATES = [60, 90, 120];

export function refreshChoices(range: { min: number | null; max: number | null } | null): number[] {
  if (range?.min == null || range.max == null) return [];
  const between = COMMON_RATES.filter((hz) => hz > range.min! && hz < range.max!);
  return [...new Set([range.min, ...between, range.max])];
}

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

export interface ColoresCaps {
  color?: boolean;
  zones?: number;
  maxBrightness?: number;
  supportedEffects?: string[];
  batteryMode?: boolean;
  temperatureMode?: boolean;
  performanceMode?: boolean;
  clockMode?: boolean;
  audioMode?: boolean;
  ambilight?: boolean;
}

export interface ColoresState {
  power: boolean;
  brightness: number;
  mode: string;
  color: Rgb;
  gradient: Rgb[];
  effect: { id: string; speed: number; useGradient: boolean };
  capabilities: ColoresCaps;
  profileContext?: { scope: "global" | "game"; appKey: string | null; followsGlobal: boolean };
}

/** Same mode list Colores offers in its own panel for these capabilities. */
export function coloresModes(caps: ColoresCaps | null | undefined): string[] {
  if (!caps?.color) return [];
  const modes = ["solid"];
  if ((caps.zones ?? 0) >= 1) modes.push("gradient");
  modes.push("effect");
  if (caps.batteryMode) modes.push("battery");
  if (caps.temperatureMode) modes.push("temperature");
  if (caps.performanceMode) modes.push("performance");
  if (caps.clockMode) modes.push("clock");
  if (caps.audioMode) modes.push("vu");
  if (caps.ambilight) modes.push("ambient");
  return modes;
}

export const COLORES_EFFECTS = ["breathing", "rainbow", "wave", "cycle", "spiral", "comet", "sparkle", "ripple", "aurora"];

export function coloresEffects(caps: ColoresCaps | null | undefined): string[] {
  const supported = caps?.supportedEffects ?? [];
  return supported.length ? COLORES_EFFECTS.filter((id) => supported.includes(id)) : COLORES_EFFECTS;
}

/** The profile that is lit right now, so a change lands where it is visible. */
export function coloresTarget(state: ColoresState): [scope: "global" | "game", appKey: string | null] {
  const ctx = state.profileContext;
  if (ctx?.scope === "game" && ctx.appKey && !ctx.followsGlobal) return ["game", ctx.appKey];
  return ["global", null];
}

/** Colores keeps brightness as a percentage; capabilities.maxBrightness is the LED driver's own scale. */
export const COLORES_BRIGHTNESS_MAX = 100;

const rgbCss = ({ r, g, b }: Rgb) => `rgb(${r},${g},${b})`;
const SPECTRUM = "linear-gradient(90deg,#ff4d5e,#ffd93d,#4cd964,#4ea1ff,#a463f2,#ff4d5e)";

/** What the lights look like right now, as a CSS background for the tile's strip. */
export function lightsSwatch(state: ColoresState | null): string | null {
  if (!state || !state.power) return null;
  if (state.mode === "solid") return rgbCss(state.color);
  if (state.mode === "gradient" && state.gradient.length > 1) {
    return `linear-gradient(90deg,${state.gradient.map(rgbCss).join(",")})`;
  }
  if (state.mode === "effect" && state.effect.useGradient && state.gradient.length > 1) {
    return `linear-gradient(90deg,${state.gradient.map(rgbCss).join(",")})`;
  }
  if (state.mode === "effect" && state.effect.id === "breathing") return rgbCss(state.color);
  return SPECTRUM;
}

export const SWATCHES: Rgb[] = [
  { r: 255, g: 59, b: 48 },
  { r: 255, g: 149, b: 0 },
  { r: 255, g: 214, b: 10 },
  { r: 52, g: 199, b: 89 },
  { r: 10, g: 132, b: 255 },
  { r: 175, g: 82, b: 222 },
  { r: 255, g: 255, b: 255 },
];

export const sameRgb = (a: Rgb, b: Rgb): boolean => a.r === b.r && a.g === b.g && a.b === b.b;
