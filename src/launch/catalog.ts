// The launch-option pill catalog + the pill→token orchestration. Pure (no @decky)
// so it's unit-testable. The catalog is the single source of truth for which
// options we offer; compose.ts is the token engine underneath.
//
// Composition model: the user's ORIGINAL string is the baseline (it may carry
// EmuDeck/SRM content we don't own). To recompute we clone the baseline, strip
// every token WE own, then re-add the active selections in canonical order —
// idempotent, and anything unknown is preserved untouched.

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
export type PillGroup = "perf" | "fps" | "langStart" | "advanced";
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
  group: PillGroup;
  kind: PillKind;
  labelKey: string;
  /** Availability gate — the pill shows disabled when the tool isn't detected. */
  requires?: ToolKey;
  advanced?: boolean;
  // env pills
  envName?: string;
  envValue?: string; // fixed value (simple env toggle)
  // wrapper pills
  wrapper?: string;
  // arg pills (single flag)
  arg?: string;
  // value pills (kind env → sets envName; kind arg → adds one of the flags)
  options?: PillOption[];
}

// A pill's on/off (or chosen value). true/undefined for toggles; the chosen value
// string for value pills (raw, so a value outside our options is still preserved).
export type Selections = Record<string, string | boolean>;

// Wrappers are listed outer→inner: gamemoderun wraps mangohud wraps ~/lsfg wraps
// the game. We add them in this array order, so the chain is canonical and any
// pre-existing (unknown) wrapper stays outermost.
export const CATALOG: Pill[] = [
  // ── Rendimiento (curado) ────────────────────────────────────────────────
  { id: "gamemode", group: "perf", kind: "wrapper", wrapper: "gamemoderun", requires: "gamemode", labelKey: "params.pill.gamemode" },
  { id: "mangohud", group: "perf", kind: "wrapper", wrapper: "mangohud", requires: "mangohud", labelKey: "params.pill.mangohud" },
  { id: "lsfg", group: "perf", kind: "wrapper", wrapper: "~/lsfg", requires: "lsfg", labelKey: "params.pill.lsfg" },
  // ── Límite de FPS (valor) ───────────────────────────────────────────────
  {
    id: "fpsLimit", group: "fps", kind: "env", envName: "DXVK_FRAME_RATE",
    labelKey: "params.pill.fps",
    options: [
      { value: "30", labelKey: "params.fps.30" },
      { value: "40", labelKey: "params.fps.40" },
      { value: "60", labelKey: "params.fps.60" },
      { value: "90", labelKey: "params.fps.90" },
      { value: "120", labelKey: "params.fps.120" },
    ],
  },
  // ── Idioma · Inicio (curado) ────────────────────────────────────────────
  { id: "langEs", group: "langStart", kind: "env", envName: "LANG", envValue: "es_ES.UTF-8", labelKey: "params.pill.langEs" },
  { id: "noVideo", group: "langStart", kind: "arg", arg: "-novid", labelKey: "params.pill.novid" },
  // ── Avanzado ──────────────────────────────────────────────────────────────
  { id: "protonLog", group: "advanced", kind: "env", envName: "PROTON_LOG", envValue: "1", advanced: true, labelKey: "params.pill.protonLog" },
  { id: "protonNoFsync", group: "advanced", kind: "env", envName: "PROTON_NO_FSYNC", envValue: "1", advanced: true, labelKey: "params.pill.protonNoFsync" },
  { id: "protonNoNtsync", group: "advanced", kind: "env", envName: "PROTON_NO_NTSYNC", envValue: "1", advanced: true, labelKey: "params.pill.protonNoNtsync" },
  { id: "protonWined3d", group: "advanced", kind: "env", envName: "PROTON_USE_WINED3D", envValue: "1", advanced: true, labelKey: "params.pill.protonWined3d" },
  { id: "protonLaa", group: "advanced", kind: "env", envName: "PROTON_FORCE_LARGE_ADDRESS_AWARE", envValue: "1", advanced: true, labelKey: "params.pill.protonLaa" },
  {
    id: "renderer", group: "advanced", kind: "arg", advanced: true,
    labelKey: "params.pill.renderer",
    options: [
      { value: "-vulkan", labelKey: "params.renderer.vulkan" },
      { value: "-dx11", labelKey: "params.renderer.dx11" },
      { value: "-dx12", labelKey: "params.renderer.dx12" },
    ],
  },
];

export const GROUP_ORDER: PillGroup[] = ["perf", "fps", "langStart", "advanced"];

/** Whether a pill is usable on this host (tool present, or no tool needed). */
export function isPillAvailable(pill: Pill, tools: LaunchTools | null): boolean {
  if (!pill.requires) return true;
  return !!tools && !!tools[pill.requires];
}

function isActive(sel: string | boolean | undefined): boolean {
  return sel !== undefined && sel !== false;
}

/** The value an env pill expects for its "on" state (fixed value, or "1"). */
function fixedEnvValue(pill: Pill): string {
  return pill.envValue ?? "1";
}

/** Remove the env/arg tokens a pill owns. A fixed-value env (LANG, PROTON_LOG=1)
 *  is only stripped when its current value is OURS — so a user's own
 *  `LANG=fr_FR` is never clobbered. A value pill (DXVK_FRAME_RATE) owns the whole
 *  variable. Wrappers are handled position-preserving in buildLaunchOptions. */
function stripPill(p: Parsed, pill: Pill): Parsed {
  if (pill.kind === "env" && pill.envName) {
    if (pill.options) p = setEnv(p, pill.envName, null);
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
    p = setEnv(p, pill.envName, pill.options ? String(sel) : fixedEnvValue(pill));
  } else if (pill.kind === "arg") {
    const flag = pill.options ? String(sel) : pill.arg;
    if (flag) p = addArg(p, flag);
  }
  return p;
}

/**
 * Read which pills are active in the baseline (drives the editor's initial
 * state). Value pills return their raw current value (so a value outside our
 * option set is preserved). A fixed-value env is active only when its value
 * matches ours (a user's `LANG=fr_FR` reads as off, not our Spanish pill).
 */
export function detectSelections(baseline: Parsed, catalog: Pill[] = CATALOG): Selections {
  const out: Selections = {};
  for (const pill of catalog) {
    if (pill.kind === "env" && pill.envName) {
      const v = getEnv(baseline, pill.envName);
      if (pill.options) {
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
      out.add(envToken(pill.envName, pill.options ? String(sel) : fixedEnvValue(pill)));
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
 * malformed baseline is returned untouched.
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
  for (const pill of catalog) {
    const sel = selections[pill.id];
    if (!isActive(sel)) continue;
    if (pill.kind === "wrapper" && pill.wrapper) p = addWrapper(p, pill.wrapper);
    else p = addPill(p, pill, sel);
  }
  return serialize(p);
}
