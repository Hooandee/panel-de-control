import { addArg, getEnv, hasArg, parse, removeArg, serialize, setEnv } from "../launch/compose";
import type { BuildInfo, EasyMode, Quality, Sharpness, UpscalerChoice } from "./types";

const OVERRIDES = "WINEDLLOVERRIDES";

export const EASY_MODES: EasyMode[] = ["game", "image", "balanced", "fps"];
export const QUALITIES: Quality[] = ["quality", "balanced", "performance", "ultra"];
export const SHARPNESS: Sharpness[] = ["off", "soft", "high"];
export const QUALITY_RATIO: Record<Quality, number> = { quality: 1.5, balanced: 1.7, performance: 2.0, ultra: 3.0 };

const EASY: Record<EasyMode, { quality: Quality | null; sharpness: Sharpness }> = {
  game: { quality: null, sharpness: "soft" },
  image: { quality: "quality", sharpness: "soft" },
  balanced: { quality: "balanced", sharpness: "soft" },
  fps: { quality: "performance", sharpness: "high" },
};

export function easyChoice(mode: EasyMode, preferred: string, fg: "on" | "off" = "off"): UpscalerChoice {
  return { build: preferred, ...EASY[mode], fg };
}

/** The easy preset a choice equals, or null once the user has changed any card. */
export function easyModeOf(choice: UpscalerChoice, preferred: string): EasyMode | null {
  if (choice.build !== preferred) return null;
  return EASY_MODES.find((mode) => EASY[mode].quality === choice.quality && EASY[mode].sharpness === choice.sharpness) ?? null;
}

export function renderHeight(outputHeight: number, quality: Quality): number {
  return Math.round(outputHeight / QUALITY_RATIO[quality]);
}

/** What runs, as short as a cover allows: the family and version, with Lite when FSR 4 runs its Lite model. */
export function badgeLabel(build: Pick<BuildInfo, "family" | "version" | "models"> | undefined, model: string | null | undefined, fallback: string): { full: string; short: string } {
  if (!build) return { full: fallback, short: fallback };
  if (build.family === "proton") return { full: build.version, short: build.version };
  const family = build.family === "xess" ? "XeSS" : build.family === "helixsr" ? "HLX" : "FSR";
  const lite = build.models?.includes("lite") && model !== "full" ? " Lite" : "";
  const major = build.version.split(".")[0];
  return { full: `${family} ${build.version}${lite}`.trim(), short: `${family} ${major}${lite}`.trim() };
}

export function buildLabel(build: Pick<BuildInfo, "family" | "version"> & { channel?: BuildInfo["channel"] }): string {
  const name = build.family === "xess" ? `XeSS ${build.version}`
    : build.family === "helixsr" ? `HLX ${build.version}`
    : build.family === "proton" ? `${build.version} (Proton)` : `FSR ${build.version}`;
  return build.channel === "beta" ? `${name} Beta` : name;
}

/** Why a build cannot go into this game, or null. HLX FSR 4 and Proton's FSR 4 only replace a game's own FSR 3.1. */
export function buildBlocker(
  build: Pick<BuildInfo, "way" | "engine">, inputs: Record<string, unknown>, protonEnv: string | null = null,
): "needsFsr31" | "needsProton" | null {
  const replacesFsr = build.way === "fsr" || build.engine === "proton";
  if (replacesFsr && !("fsr31" in inputs)) return "needsFsr31";
  if (build.engine === "proton" && !protonEnv) return "needsProton";
  return null;
}

/** The FSR 4 switch the game's Proton understands on this GPU, or null. */
export function protonFsr4Env(pills: { exclusiveGroup?: string; envName?: string }[], visible: (pill: never) => boolean): string | null {
  const pill = pills.find((p) => p.exclusiveGroup === "fsr4-upgrade" && visible(p as never));
  return pill?.envName ?? null;
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

/** Launch options after adding Panel's overrides and recipe args; `added` lists args that were not there. */
export function applyLaunch(launch: string, overrides: string[], args: string[]): { value: string; added: string[] } | null {
  let value: string | null = launch;
  for (const override of overrides) {
    value = withOverride(value, override);
    if (value === null) return null;
  }
  let parsed = parse(value);
  if (parsed.malformed) return null;
  const added = args.filter((arg) => !hasArg(parsed, arg));
  for (const arg of added) parsed = addArg(parsed, arg);
  return { value: serialize(parsed), added };
}

export function revertLaunch(launch: string, overrides: string[], added: string[]): string | null {
  let value: string | null = launch;
  for (const override of overrides) {
    value = withoutOverride(value, override);
    if (value === null) return null;
  }
  let parsed = parse(value);
  if (parsed.malformed) return null;
  for (const arg of added) parsed = removeArg(parsed, arg);
  return serialize(parsed);
}

/** Launch options with each `env` key set (a string) or removed (null); null when unsafe to edit. */
export function withEnv(launch: string, env: Record<string, string | null>): string | null {
  let parsed = parse(launch);
  if (parsed.malformed) return null;
  for (const [name, value] of Object.entries(env)) parsed = setEnv(parsed, name, value);
  return serialize(parsed);
}

export interface LaunchChange {
  overrides?: string[];
  args?: string[];
  removed_overrides?: string[];
  removed_args?: string[];
  env?: Record<string, string | null>;
}

/** Which of these overrides and variables the launch options already carry, so removal leaves them alone. */
export function alreadyThere(launch: string, overrides: string[], env: Record<string, string | null>): { overrides: string[]; env: string[] } {
  const parsed = parse(launch);
  const current = parsed.malformed ? null : split(getEnv(parsed, OVERRIDES));
  return {
    overrides: overrides.filter((o) => {
      const [dll, mode] = o.split("=");
      return !!current && current.mode === mode && current.names.includes(dll);
    }),
    env: Object.keys(env).filter((name) => !parsed.malformed && getEnv(parsed, name) !== null),
  };
}

/** Launch options after an install (what it adds, minus what the install it replaced left) or a removal. */
export function launchAfterJob(launch: string, change: LaunchChange, kind: "install" | "uninstall"): {
  value: string; added: string[]; addedOverrides: string[]; addedEnv: string[];
} | null {
  const reverted = kind === "install"
    ? revertLaunch(launch, change.removed_overrides ?? [], change.removed_args ?? [])
    : revertLaunch(launch, change.overrides ?? [], change.args ?? []);
  if (reverted === null) return null;
  const applied = kind === "install" ? applyLaunch(reverted, change.overrides ?? [], change.args ?? []) : { value: reverted, added: [] };
  if (applied === null) return null;
  const value = change.env && Object.keys(change.env).length ? withEnv(applied.value, change.env) : applied.value;
  if (value === null) return null;
  const wanted = Object.fromEntries(Object.entries(change.env ?? {}).filter(([, v]) => v !== null));
  const before = alreadyThere(reverted, change.overrides ?? [], wanted);
  return {
    value, added: applied.added,
    addedOverrides: kind === "install" ? (change.overrides ?? []).filter((o) => !before.overrides.includes(o)) : [],
    addedEnv: kind === "install" ? Object.keys(wanted).filter((k) => !before.env.includes(k)) : [],
  };
}

export interface PaceSample { done: number; at: number }

/** Bytes per second and seconds left from two progress samples, smoothed with the previous rate. */
export function downloadPace(previous: PaceSample, current: PaceSample, total: number, lastRate = 0): { rate: number; eta: number | null } {
  const seconds = (current.at - previous.at) / 1000;
  const instant = seconds > 0 ? Math.max(0, current.done - previous.done) / seconds : 0;
  const rate = lastRate > 0 ? lastRate * 0.7 + instant * 0.3 : instant;
  return { rate, eta: rate > 0 ? Math.ceil((total - current.done) / rate) : null };
}

/** On the Deck OptiFG costs too much on top of upscaling (40 to 50 FPS measured) while Lossless reached 60. */
export function recommendedPick(gpu: string, routes: Record<string, unknown>, lossless: boolean): "lsfg-2" | "game" | null {
  if (gpu === "rdna2" && lossless) return "lsfg-2";
  if ("game" in routes) return "game";
  if (lossless) return "lsfg-2";
  return null;
}
