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
  /** Plain-language "what it does" line (required — the whole point of the row). */
  descKey: string;
  /** The real token/flag, shown small next to the title for those who know it. */
  raw?: string;
  /** Honest availability gate — the row shows disabled when the tool isn't detected. */
  requires?: ToolKey;
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
  { id: "mangohud", section: "common", subgroup: "params.sub.perf", kind: "wrapper", wrapper: "mangohud", raw: "mangohud", requires: "mangohud", labelKey: "params.pill.mangohud", descKey: "params.pill.mangohud.desc" },
  { id: "gamemode", section: "common", subgroup: "params.sub.perf", kind: "wrapper", wrapper: "gamemoderun", raw: "gamemoderun", requires: "gamemode", labelKey: "params.pill.gamemode", descKey: "params.pill.gamemode.desc" },
  { id: "lsfg", section: "common", subgroup: "params.sub.perf", kind: "wrapper", wrapper: "~/lsfg", raw: "~/lsfg", requires: "lsfg", labelKey: "params.pill.lsfg", descKey: "params.pill.lsfg.desc" },
  {
    id: "fpsLimit", section: "common", subgroup: "params.sub.fps", kind: "env", envName: "DXVK_FRAME_RATE",
    raw: "DXVK_FRAME_RATE", labelKey: "params.pill.fps", descKey: "params.pill.fps.desc",
    options: [
      { value: "30", labelKey: "params.fps.30" },
      { value: "40", labelKey: "params.fps.40" },
      { value: "60", labelKey: "params.fps.60" },
      { value: "90", labelKey: "params.fps.90" },
      { value: "120", labelKey: "params.fps.120" },
    ],
  },
  { id: "langEs", section: "common", subgroup: "params.sub.lang", kind: "env", envName: "LANG", envValue: "es_ES.UTF-8", raw: "LANG", labelKey: "params.pill.langEs", descKey: "params.pill.langEs.desc" },
  { id: "noVideo", section: "common", subgroup: "params.sub.startup", kind: "arg", arg: "-novid", raw: "-novid", labelKey: "params.pill.novid", descKey: "params.pill.novid.desc" },

  // ── Avanzado · Proton (compatibilidad) ────────────────────────────────────
  { id: "protonLaa", section: "advanced", subgroup: "params.sub.proton", kind: "env", envName: "PROTON_FORCE_LARGE_ADDRESS_AWARE", envValue: "1", raw: "PROTON_FORCE_LARGE_ADDRESS_AWARE", labelKey: "params.pill.protonLaa", descKey: "params.pill.protonLaa.desc" },
  { id: "protonNoFsync", section: "advanced", subgroup: "params.sub.proton", kind: "env", envName: "PROTON_NO_FSYNC", envValue: "1", raw: "PROTON_NO_FSYNC", labelKey: "params.pill.protonNoFsync", descKey: "params.pill.protonNoFsync.desc" },
  { id: "protonNoNtsync", section: "advanced", subgroup: "params.sub.proton", kind: "env", envName: "PROTON_NO_NTSYNC", envValue: "1", raw: "PROTON_NO_NTSYNC", labelKey: "params.pill.protonNoNtsync", descKey: "params.pill.protonNoNtsync.desc" },
  { id: "protonWined3d", section: "advanced", subgroup: "params.sub.proton", kind: "env", envName: "PROTON_USE_WINED3D", envValue: "1", raw: "PROTON_USE_WINED3D", labelKey: "params.pill.protonWined3d", descKey: "params.pill.protonWined3d.desc" },
  { id: "protonLog", section: "advanced", subgroup: "params.sub.proton", kind: "env", envName: "PROTON_LOG", envValue: "1", raw: "PROTON_LOG", labelKey: "params.pill.protonLog", descKey: "params.pill.protonLog.desc" },

  // ── Avanzado · Renderizado ────────────────────────────────────────────────
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
];

/** Sub-group order within each section (kept stable; pills render grouped by these). */
export const SUBGROUP_ORDER: Record<Section, string[]> = {
  common: ["params.sub.perf", "params.sub.fps", "params.sub.lang", "params.sub.startup"],
  advanced: ["params.sub.proton", "params.sub.render", "params.sub.dlls", "params.sub.gameArgs"],
};

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
