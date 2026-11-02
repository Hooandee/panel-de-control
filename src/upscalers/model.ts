import { getEnv, parse, serialize, setEnv } from "../launch/compose";
import type { BuildInfo, EasyMode, Quality, Sharpness, UpscalerChoice } from "./types";

const OVERRIDES = "WINEDLLOVERRIDES";

export const EASY_MODES: EasyMode[] = ["image", "balanced", "fps"];
export const QUALITIES: Quality[] = ["quality", "balanced", "performance", "ultra"];
export const SHARPNESS: Sharpness[] = ["off", "soft", "high"];
export const QUALITY_RATIO: Record<Quality, number> = { quality: 1.5, balanced: 1.7, performance: 2.0, ultra: 3.0 };

const EASY: Record<EasyMode, { quality: Quality; sharpness: Sharpness }> = {
  image: { quality: "quality", sharpness: "soft" },
  balanced: { quality: "balanced", sharpness: "soft" },
  fps: { quality: "performance", sharpness: "high" },
};

export function easyChoice(mode: EasyMode, preferred: string): UpscalerChoice {
  return { build: preferred, ...EASY[mode] };
}

/** The easy preset a choice equals, or null once the user has changed any card. */
export function easyModeOf(choice: UpscalerChoice, preferred: string): EasyMode | null {
  if (choice.build !== preferred) return null;
  return EASY_MODES.find((mode) => EASY[mode].quality === choice.quality && EASY[mode].sharpness === choice.sharpness) ?? null;
}

export function renderHeight(outputHeight: number, quality: Quality): number {
  return Math.round(outputHeight / QUALITY_RATIO[quality]);
}

export function buildLabel(build: Pick<BuildInfo, "family" | "version">): string {
  return build.family === "xess" ? `XeSS ${build.version}` : `FSR ${build.version}`;
}

// The composer treats `;` as a shell operator, so overrides stay one `names=mode` entry:
// Wine accepts several DLL names sharing a mode, separated by commas.
function split(value: string | null): { names: string[]; mode: string } | null {
  const raw = (value ?? "").replace(/^"|"$/g, "").trim();
  if (!raw) return { names: [], mode: "" };
  const eq = raw.indexOf("=");
  if (eq <= 0) return null;
  return { names: raw.slice(0, eq).split(",").map((n) => n.trim()).filter(Boolean), mode: raw.slice(eq + 1) };
}

/** Launch options with `override` (e.g. `dxgi=n,b`) in WINEDLLOVERRIDES; null when it cannot be merged safely. */
export function withOverride(launch: string, override: string): string | null {
  const parsed = parse(launch);
  if (parsed.malformed) return null;
  const [dll, mode] = override.split("=");
  const current = split(getEnv(parsed, OVERRIDES));
  if (!current) return null;
  const others = current.names.filter((name) => name !== dll);
  if (others.length && current.mode !== mode) return null;
  return serialize(setEnv(parsed, OVERRIDES, `"${[...others, dll].join(",")}=${mode}"`));
}

export function withoutOverride(launch: string, override: string): string | null {
  const parsed = parse(launch);
  if (parsed.malformed) return null;
  const [dll, mode] = override.split("=");
  const current = split(getEnv(parsed, OVERRIDES));
  if (!current || current.mode !== mode || !current.names.includes(dll)) return serialize(parsed);
  const others = current.names.filter((name) => name !== dll);
  return serialize(setEnv(parsed, OVERRIDES, others.length ? `"${others.join(",")}=${mode}"` : null));
}

export function megabytes(bytes: number): string {
  return (bytes / (1024 * 1024)).toFixed(0);
}
