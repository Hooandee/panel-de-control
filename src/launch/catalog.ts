// The launch-option pill catalog + the pill→token orchestration. Pure (no @decky)
// so it's unit-testable. The catalog is the single source of truth for which
// options we offer; compose.ts is the token engine underneath.
//
// Composition model: the user's ORIGINAL string is the baseline (it may carry
// EmuDeck/SRM content we don't own). To recompute we clone the baseline, strip
// every token WE own, then re-add the active selections — preserving anything
// unknown. Env/arg tokens are order-independent; wrappers keep their position.

import {
  Parsed,
  getEnv,
  setEnv,
  hasWrapper,
  addWrapper,
  removeWrapper,
  hasArg,
  addArg,
  removeArg,
  serialize,
  envToken,
} from "./compose";
import { GpuGen } from "./proton";
import { isCustomPillId } from "./customVars";

export type PillKind = "env" | "wrapper" | "arg";
export type Section = "common" | "advanced";
export type ToolKey = "lsfg" | "mangohud" | "gamemode";

/** Detected host tools + distro — drives honest availability + the locale caveat. */
export interface LaunchTools {
  lsfg: boolean;
  mangohud: boolean;
  gamemode: boolean;
  gamescope: boolean;
  distro: string; // "steamos" | "bazzite" | "cachyos" | "other"
  locale_reliable: boolean;
}

export interface PillOption {
  value: string;
  labelKey: string;
}

export interface Pill {
  id: string;
  section: Section;
  /** i18n key of the sub-group heading this pill sits under. */
  subgroup: string;
  kind: PillKind;
  labelKey: string;
  /** Raw user-visible label, used instead of labelKey for user-defined pills. */
  label?: string;
  /** Plain-language "what it does" line (required — the whole point of the row). */
  descKey: string;
  /** Raw description, used instead of descKey for user-defined pills. */
  desc?: string;
  /** Longer explanation + example, shown when the row is expanded. Derived as
   *  descKey with ".desc"→".help" when absent. */
  helpKey?: string;
  /** Safe, broadly-useful pick — gets a "Recomendado" badge + seeds "Empezar aquí". */
  recommended?: boolean;
  /** The real token/flag, shown small next to the title for those who know it. */
  raw?: string;
  /** Honest availability gate — the row shows disabled when the tool isn't detected. */
  requires?: ToolKey;
  /** Show only on these GPU generations (absent = any). FSR4 uses this to pick the
   *  right per-GPU env var: RDNA4 vs RDNA3 need different Proton flags. */
  gpus?: GpuGen[];
  // env pills
  envName?: string;
  envValue?: string; // fixed value (simple env toggle)
  /** Free-text env (WINEDLLOVERRIDES): the user types the value; we own the whole var. */
  freeText?: boolean;
  placeholderKey?: string;
  // wrapper pills
  wrapper?: string;
  // arg pills (single flag)
  arg?: string;
  // value pills (env → sets envName; arg → adds one of the flags)
  options?: PillOption[];
}

// A pill's on/off (or chosen/typed value). true/undefined for toggles; the chosen
// value string for value/free-text pills (raw, so anything outside our set is kept).
export type Selections = Record<string, string | boolean>;

// Usage counts per pill id (how often the user applies each) → the "Frecuentes"
// shortcut row surfaces the ones they actually use.
export type Usage = Record<string, number>;

// Wrappers are listed outer→inner: gamemoderun wraps mangohud wraps ~/lsfg wraps
// the game. Added in this array order, so a newly-enabled wrapper lands in the
// right place while any pre-existing (unknown) wrapper stays outermost.
export const CATALOG: Pill[] = [
  // ── Común ────────────────────────────────────────────────────────────────
  { id: "mangohud", section: "common", recommended: true, subgroup: "params.sub.perf", kind: "wrapper", wrapper: "mangohud", raw: "mangohud", requires: "mangohud", labelKey: "params.pill.mangohud", descKey: "params.pill.mangohud.desc" },
  { id: "gamemode", section: "common", subgroup: "params.sub.perf", kind: "wrapper", wrapper: "gamemoderun", raw: "gamemoderun", requires: "gamemode", labelKey: "params.pill.gamemode", descKey: "params.pill.gamemode.desc" },
  { id: "lsfg", section: "common", subgroup: "params.sub.perf", kind: "wrapper", wrapper: "~/lsfg", raw: "~/lsfg", requires: "lsfg", labelKey: "params.pill.lsfg", descKey: "params.pill.lsfg.desc" },
  { id: "langEs", section: "common", subgroup: "params.sub.lang", kind: "env", envName: "LANG", envValue: "es_ES.UTF-8", raw: "LANG", labelKey: "params.pill.langEs", descKey: "params.pill.langEs.desc" },
  { id: "noVideo", section: "common", recommended: true, subgroup: "params.sub.startup", kind: "arg", arg: "-novid", raw: "-novid", labelKey: "params.pill.novid", descKey: "params.pill.novid.desc" },

  // ── Avanzado · Proton (compatibilidad) ────────────────────────────────────
  { id: "protonLaa", section: "advanced", recommended: true, subgroup: "params.sub.proton", kind: "env", envName: "PROTON_FORCE_LARGE_ADDRESS_AWARE", envValue: "1", raw: "PROTON_FORCE_LARGE_ADDRESS_AWARE", labelKey: "params.pill.protonLaa", descKey: "params.pill.protonLaa.desc" },
  { id: "protonNoFsync", section: "advanced", subgroup: "params.sub.proton", kind: "env", envName: "PROTON_NO_FSYNC", envValue: "1", raw: "PROTON_NO_FSYNC", labelKey: "params.pill.protonNoFsync", descKey: "params.pill.protonNoFsync.desc" },
  { id: "protonNoNtsync", section: "advanced", subgroup: "params.sub.proton", kind: "env", envName: "PROTON_NO_NTSYNC", envValue: "1", raw: "PROTON_NO_NTSYNC", labelKey: "params.pill.protonNoNtsync", descKey: "params.pill.protonNoNtsync.desc" },
  { id: "protonWined3d", section: "advanced", subgroup: "params.sub.proton", kind: "env", envName: "PROTON_USE_WINED3D", envValue: "1", raw: "PROTON_USE_WINED3D", labelKey: "params.pill.protonWined3d", descKey: "params.pill.protonWined3d.desc" },
  { id: "protonLog", section: "advanced", subgroup: "params.sub.proton", kind: "env", envName: "PROTON_LOG", envValue: "1", raw: "PROTON_LOG", labelKey: "params.pill.protonLog", descKey: "params.pill.protonLog.desc" },
  { id: "heapDelayFree", section: "advanced", subgroup: "params.sub.proton", kind: "env", envName: "PROTON_HEAP_DELAY_FREE", envValue: "1", raw: "PROTON_HEAP_DELAY_FREE", labelKey: "params.pill.heapDelayFree", descKey: "params.pill.heapDelayFree.desc" },

  // ── Avanzado · Escalado (según versión + GPU) ─────────────────────────────
  // FSR4 needs a different Proton env var per GPU: RDNA4 vs RDNA3 (the RDNA3 path
  // adds the wmma workaround). Two pills, same label — only one shows per device.
  { id: "fsr4", section: "advanced", subgroup: "params.sub.upscaling", kind: "env", envName: "PROTON_FSR4_UPGRADE", envValue: "1", raw: "PROTON_FSR4_UPGRADE", gpus: ["rdna4"], labelKey: "params.pill.fsr4", descKey: "params.pill.fsr4.desc" },
  { id: "fsr4Rdna3", section: "advanced", subgroup: "params.sub.upscaling", kind: "env", envName: "PROTON_FSR4_RDNA3_UPGRADE", envValue: "1", raw: "PROTON_FSR4_RDNA3_UPGRADE", gpus: ["rdna3"], labelKey: "params.pill.fsr4", descKey: "params.pill.fsr4.desc" },
  { id: "optiscaler", section: "advanced", subgroup: "params.sub.upscaling", kind: "env", envName: "PROTON_USE_OPTISCALER", envValue: "1", raw: "PROTON_USE_OPTISCALER", labelKey: "params.pill.optiscaler", descKey: "params.pill.optiscaler.desc" },

  // ── Avanzado · Pantalla ───────────────────────────────────────────────────
  { id: "protonHdr", section: "advanced", subgroup: "params.sub.display", kind: "env", envName: "PROTON_ENABLE_HDR", envValue: "1", raw: "PROTON_ENABLE_HDR", labelKey: "params.pill.protonHdr", descKey: "params.pill.protonHdr.desc" },
  { id: "protonWayland", section: "advanced", subgroup: "params.sub.display", kind: "env", envName: "PROTON_ENABLE_WAYLAND", envValue: "1", raw: "PROTON_ENABLE_WAYLAND", labelKey: "params.pill.protonWayland", descKey: "params.pill.protonWayland.desc" },

  // ── Avanzado · Renderizado ────────────────────────────────────────────────
  { id: "noDxr", section: "advanced", recommended: true, subgroup: "params.sub.render", kind: "env", envName: "VKD3D_CONFIG", envValue: "nodxr", raw: "VKD3D_CONFIG", labelKey: "params.pill.noDxr", descKey: "params.pill.noDxr.desc" },
  { id: "dxvkD3d8", section: "advanced", subgroup: "params.sub.render", kind: "env", envName: "PROTON_DXVK_D3D8", envValue: "1", raw: "PROTON_DXVK_D3D8", labelKey: "params.pill.dxvkD3d8", descKey: "params.pill.dxvkD3d8.desc" },
  {
    id: "renderer", section: "advanced", subgroup: "params.sub.render", kind: "arg",
    labelKey: "params.pill.renderer", descKey: "params.pill.renderer.desc",
    options: [
      { value: "-vulkan", labelKey: "params.renderer.vulkan" },
      { value: "-dx11", labelKey: "params.renderer.dx11" },
      { value: "-dx12", labelKey: "params.renderer.dx12" },
    ],
  },
  {
    id: "windowMode", section: "advanced", subgroup: "params.sub.render", kind: "arg",
    labelKey: "params.pill.windowMode", descKey: "params.pill.windowMode.desc",
    options: [
      { value: "-windowed", labelKey: "params.window.windowed" },
      { value: "-fullscreen", labelKey: "params.window.fullscreen" },
    ],
  },

  // ── Avanzado · Librerías (DLL) ────────────────────────────────────────────
  { id: "winedll", section: "advanced", subgroup: "params.sub.dlls", kind: "env", envName: "WINEDLLOVERRIDES", freeText: true, raw: "WINEDLLOVERRIDES", placeholderKey: "params.pill.winedll.placeholder", labelKey: "params.pill.winedll", descKey: "params.pill.winedll.desc" },

  // ── Avanzado · Opciones del juego ─────────────────────────────────────────
  { id: "noJoy", section: "advanced", subgroup: "params.sub.gameArgs", kind: "arg", arg: "-nojoy", raw: "-nojoy", labelKey: "params.pill.nojoy", descKey: "params.pill.nojoy.desc" },
  { id: "highPriority", section: "advanced", subgroup: "params.sub.gameArgs", kind: "arg", arg: "-high", raw: "-high", labelKey: "params.pill.high", descKey: "params.pill.high.desc" },
  { id: "preferSdl", section: "advanced", subgroup: "params.sub.gameArgs", kind: "env", envName: "PROTON_PREFER_SDL", envValue: "1", raw: "PROTON_PREFER_SDL", labelKey: "params.pill.preferSdl", descKey: "params.pill.preferSdl.desc" },
];

/** Sub-group order within each section (kept stable; pills render grouped by these). */
export const SUBGROUP_ORDER: Record<Section, string[]> = {
  common: ["params.sub.perf", "params.sub.lang", "params.sub.startup"],
  advanced: ["params.sub.proton", "params.sub.upscaling", "params.sub.display", "params.sub.render", "params.sub.dlls", "params.sub.gameArgs", "params.sub.custom"],
};

/** Whether a pill applies here. A PROTON_* env pill shows only if the game's
 *  Proton build actually supports that variable (`supportedEnvs`, read from its
 *  script) — self-updating per version, never faking unsupported options. GPU-
 *  gated pills (FSR4) also need a matching GPU. Non-Proton pills always show.
 *  Tool availability is separate (those show disabled, not hidden). */
export function pillVisible(pill: Pill, supportedEnvs: string[], gpu: GpuGen): boolean {
  // User-defined pills aren't capability-gated (we can't verify an arbitrary var).
  if (isCustomPillId(pill.id)) return true;
  if (pill.gpus && !pill.gpus.includes(gpu)) return false;
  if (pill.kind === "env" && pill.envName?.startsWith("PROTON_") && !supportedEnvs.includes(pill.envName)) {
    return false;
  }
  return true;
}

// Wrapper chain order (outer→inner), independent of display order: gamemode wraps
// mangohud wraps lsfg wraps the game. Newly-enabled wrappers are added in this order.
const WRAPPER_PRECEDENCE: Record<string, number> = { gamemoderun: 0, mangohud: 1, "~/lsfg": 2 };

function isActive(sel: string | boolean | undefined): boolean {
  return sel !== undefined && sel !== false;
}

/** True when the pill owns its whole env variable (value pills + free-text), vs a
 *  fixed-value env we only own when the value matches ours. */
function ownsVar(pill: Pill): boolean {
  return !!pill.options || !!pill.freeText;
}

/** The value an env pill expects for its "on" state (fixed value, or "1"). */
function fixedEnvValue(pill: Pill): string {
  return pill.envValue ?? "1";
}

/** Whether a pill is usable on this host (tool present, or no tool needed). */
export function isPillAvailable(pill: Pill, tools: LaunchTools | null): boolean {
  if (!pill.requires) return true;
  return !!tools && !!tools[pill.requires];
}

/** Remove the env/arg tokens a pill owns. A fixed-value env (LANG, PROTON_LOG=1)
 *  is only stripped when its current value is OURS — so a user's own `LANG=fr_FR`
 *  is never clobbered. A value/free-text pill owns the whole variable. Wrappers
 *  are handled position-preserving in buildLaunchOptions. */
function stripPill(p: Parsed, pill: Pill): Parsed {
  if (pill.kind === "env" && pill.envName) {
    if (ownsVar(pill)) p = setEnv(p, pill.envName, null);
    else if (getEnv(p, pill.envName) === fixedEnvValue(pill)) p = setEnv(p, pill.envName, null);
  } else if (pill.kind === "arg") {
    if (pill.arg) p = removeArg(p, pill.arg);
    for (const o of pill.options ?? []) p = removeArg(p, o.value);
  }
  return p;
}

/** Add an env/arg pill's tokens for the given selection value. */
function addPill(p: Parsed, pill: Pill, sel: string | boolean): Parsed {
  if (pill.kind === "env" && pill.envName) {
    p = setEnv(p, pill.envName, ownsVar(pill) ? String(sel) : fixedEnvValue(pill));
  } else if (pill.kind === "arg") {
    const flag = pill.options ? String(sel) : pill.arg;
    if (flag) p = addArg(p, flag);
  }
  return p;
}

/**
 * Read which pills are active in the baseline (drives the editor's initial
 * state). Value/free-text pills return their raw current value (so anything
 * outside our set is preserved). A fixed-value env is active only when its value
 * matches ours (a user's `LANG=fr_FR` reads as off, not our Spanish pill).
 */
export function detectSelections(baseline: Parsed, catalog: Pill[] = CATALOG): Selections {
  const out: Selections = {};
  for (const pill of catalog) {
    if (pill.kind === "env" && pill.envName) {
      const v = getEnv(baseline, pill.envName);
      if (ownsVar(pill)) {
        if (v !== null) out[pill.id] = v;
      } else if (v === fixedEnvValue(pill)) {
        out[pill.id] = true;
      }
    } else if (pill.kind === "wrapper" && pill.wrapper) {
      if (hasWrapper(baseline, pill.wrapper)) out[pill.id] = true;
    } else if (pill.kind === "arg") {
      if (pill.options) {
        const found = pill.options.find((o) => hasArg(baseline, o.value));
        if (found) out[pill.id] = found.value;
      } else if (pill.arg && hasArg(baseline, pill.arg)) {
        out[pill.id] = true;
      }
    }
  }
  return out;
}

/** The exact token strings our ACTIVE selections contribute — lets the preview
 *  color our additions vs the user's pre-existing (preserved) content. */
export function ownedTokens(selections: Selections, catalog: Pill[] = CATALOG): Set<string> {
  const out = new Set<string>();
  for (const pill of catalog) {
    const sel = selections[pill.id];
    if (!isActive(sel)) continue;
    if (pill.kind === "env" && pill.envName) {
      out.add(envToken(pill.envName, ownsVar(pill) ? String(sel) : fixedEnvValue(pill)));
    } else if (pill.kind === "wrapper" && pill.wrapper) {
      out.add(pill.wrapper);
    } else if (pill.kind === "arg") {
      const flag = pill.options ? String(sel) : pill.arg;
      if (flag) out.add(flag);
    }
  }
  return out;
}

/**
 * Compose the final launch-options string. Env/arg tokens are strip-then-add
 * (order-independent). Wrappers are POSITION-PRESERVING: an active wrapper that's
 * already present is left where it is (so a hand-written `mangohud --dlsym` keeps
 * its argument adjacent), a deselected one is removed, and a newly-enabled one is
 * appended in canonical order. Unknown/pre-existing content is preserved. A
 * malformed baseline is returned untouched. An active free-text pill with an
 * empty value contributes nothing (we don't write `WINEDLLOVERRIDES=`).
 */
export function buildLaunchOptions(
  baseline: Parsed,
  selections: Selections,
  catalog: Pill[] = CATALOG,
): string {
  if (baseline.malformed) return serialize(baseline);
  let p = baseline;
  for (const pill of catalog) {
    const active = isActive(selections[pill.id]);
    if (pill.kind === "wrapper" && pill.wrapper) {
      if (!active) p = removeWrapper(p, pill.wrapper);
    } else {
      p = stripPill(p, pill);
    }
  }
  // Wrappers first, in chain-precedence order (a newly-enabled one lands right).
  const activeWrappers = catalog
    .filter((pill) => pill.kind === "wrapper" && pill.wrapper && isActive(selections[pill.id]))
    .sort((a, b) => (WRAPPER_PRECEDENCE[a.wrapper!] ?? 99) - (WRAPPER_PRECEDENCE[b.wrapper!] ?? 99));
  for (const pill of activeWrappers) p = addWrapper(p, pill.wrapper!);
  // Then env/arg tokens.
  for (const pill of catalog) {
    const sel = selections[pill.id];
    if (!isActive(sel) || (pill.kind === "wrapper" && pill.wrapper)) continue;
    if (pill.freeText && String(sel).trim() === "") continue; // empty free-text = off
    p = addPill(p, pill, sel);
  }
  return serialize(p);
}

/** The row's long-help i18n key (explicit helpKey, else descKey with .desc→.help). */
export function helpKeyOf(pill: Pill): string {
  return pill.helpKey ?? pill.descKey.replace(/\.desc$/, ".help");
}

/** Resolved row label/description: raw text for user-defined pills, else the i18n key. */
export function pillLabel(pill: Pill, t: (k: string) => string): string {
  return pill.label ?? t(pill.labelKey);
}
export function pillDesc(pill: Pill, t: (k: string) => string): string {
  return pill.desc ?? t(pill.descKey);
}
/** Expanded-help text: raw desc for user-defined pills (no i18n key), else the help key. */
export function pillHelp(pill: Pill, t: (k: string) => string): string {
  return isCustomPillId(pill.id) ? pill.desc ?? "" : t(helpKeyOf(pill));
}

/** Safe recommended picks that apply here — seeds "Empezar aquí" when there's no usage. */
export function recommendedPills(
  tools: LaunchTools | null,
  supportedEnvs: string[],
  gpu: GpuGen,
  n = 4,
  catalog: Pill[] = CATALOG,
): Pill[] {
  return catalog
    .filter((p) => p.recommended && isPillAvailable(p, tools) && pillVisible(p, supportedEnvs, gpu))
    .slice(0, n);
}

/** The user's most-used AVAILABLE pills (count > 0), most-first, capped at `n` —
 *  the "Frecuentes" shortcut row. Ties broken by catalog order for stability. */
export function frequentPills(
  usage: Usage,
  tools: LaunchTools | null,
  n = 4,
  catalog: Pill[] = CATALOG,
): Pill[] {
  return catalog
    .filter((p) => isPillAvailable(p, tools) && (usage[p.id] ?? 0) > 0)
    .sort((a, b) => (usage[b.id] ?? 0) - (usage[a.id] ?? 0))
    .slice(0, n);
}
