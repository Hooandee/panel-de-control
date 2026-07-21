// User-defined launch variables — a small library reusable across every game. A
// custom var is just a Pill, so it flows through the same compose engine (preserving
// foreign content, ownership rules). The definition lives global (backend store); the
// on/off is per-game, stored in Steam's launch string like any other pill.

import type { Pill } from "./catalog";

export interface CustomVarDef {
  id: string;
  /** User-visible label — raw text, not an i18n key. */
  name: string;
  kind: "env" | "arg";
  envName?: string;
  envValue?: string;
  arg?: string;
  retired?: boolean;
}

/** Marks a Pill as user-defined (skips capability gating in pillVisible). */
export const CUSTOM_PREFIX = "custom:";

export function isCustomPillId(id: string): boolean {
  return id.startsWith(CUSTOM_PREFIX);
}

const ENV_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
// Chars we can't safely place in the composed command without a shell parser:
// whitespace splits the token, quotes/backslash/operators change meaning. Rejected
// until values are auto-escaped and args are real tokens.
const UNSAFE_RE = /[\s"'\\`$;&|<>()]/;

/** The token a def owns: the env NAME, or the arg flag. */
export function customVarToken(def: CustomVarDef): string {
  return def.kind === "arg" ? (def.arg ?? "") : (def.envName ?? "");
}

/** null when valid, else a short reason. `taken` = tokens already owned by base
 *  pills or other custom vars → a duplicate would create two controls for the same
 *  token (turning one off leaves the other's, re-appearing active). Pure. */
export function validateCustomVar(def: CustomVarDef, taken: Set<string> = new Set()): string | null {
  if (!def.name.trim()) return "name";
  if (def.kind === "env") {
    if (!def.envName || !ENV_NAME_RE.test(def.envName)) return "envName";
    if (def.envValue && UNSAFE_RE.test(def.envValue)) return "unsafe";
  } else if (def.kind === "arg") {
    if (!def.arg || !def.arg.trim()) return "arg";
    if (UNSAFE_RE.test(def.arg)) return "unsafe";
  } else {
    return "kind";
  }
  if (taken.has(customVarToken(def))) return "duplicate";
  return null;
}

export function sanitizeCustomVars(defs: CustomVarDef[], taken: Set<string> = new Set()): CustomVarDef[] {
  const owned = new Set(taken);
  const out: CustomVarDef[] = [];
  for (const def of defs) {
    if (validateCustomVar(def, owned)) continue;
    out.push(def);
    owned.add(customVarToken(def));
  }
  return out;
}

export function customPillVisible(pill: Pill, selection: string | boolean | undefined): boolean {
  return !pill.retired || (selection !== undefined && selection !== false);
}

function activeDef(def: CustomVarDef): CustomVarDef {
  const { retired: _retired, ...active } = def;
  return active;
}

export function retireCustomVar(defs: CustomVarDef[], id: string): CustomVarDef[] {
  return defs.map((def) => (def.id === id ? { ...def, retired: true } : def));
}

export function saveCustomDraft(
  defs: CustomVarDef[],
  draft: CustomVarDef,
  newId: () => string,
): CustomVarDef[] {
  const cleanDraft = activeDef(draft);
  const index = defs.findIndex((def) => def.id === draft.id);
  if (index < 0) {
    const retiredIndex = defs.findIndex(
      (def) => def.retired && customVarToken(def) === customVarToken(cleanDraft),
    );
    if (retiredIndex >= 0) {
      return defs.map((def, i) => (i === retiredIndex ? { ...cleanDraft, id: def.id } : def));
    }
    return [...defs, cleanDraft];
  }
  const previous = defs[index];
  if (customVarToken(previous) === customVarToken(cleanDraft)) {
    return defs.map((def, i) => (i === index ? cleanDraft : def));
  }
  const retiredIndex = defs.findIndex(
    (def, i) => i !== index && def.retired && customVarToken(def) === customVarToken(cleanDraft),
  );
  if (retiredIndex >= 0) {
    return defs.map((def, i) => {
      if (i === retiredIndex) return { ...cleanDraft, id: def.id };
      if (i === index) return { ...def, retired: true };
      return def;
    });
  }
  return defs.flatMap((def, i) =>
    i === index ? [{ ...def, id: newId(), retired: true }, cleanDraft] : [def],
  );
}

/** Convert a definition into a catalog Pill so the engine treats it like any pill.
 *  An env var is a fixed KEY=VALUE (we own it only when the value matches ours). */
export function customVarToPill(def: CustomVarDef): Pill {
  const base = {
    id: CUSTOM_PREFIX + def.id,
    section: "advanced" as const,
    subgroup: "params.sub.custom",
    label: def.name,
    labelKey: "",
    descKey: "",
    retired: def.retired === true,
  };
  if (def.kind === "arg") {
    return { ...base, kind: "arg", arg: def.arg, raw: def.arg, desc: def.arg };
  }
  const value = def.envValue ?? "";
  return {
    ...base,
    kind: "env",
    envName: def.envName,
    envValue: value,
    raw: def.envName,
    desc: `${def.envName}=${value}`,
  };
}
