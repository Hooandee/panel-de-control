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
}

/** Marks a Pill as user-defined (skips capability gating in pillVisible). */
export const CUSTOM_PREFIX = "custom:";

export function isCustomPillId(id: string): boolean {
  return id.startsWith(CUSTOM_PREFIX);
}

const ENV_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** null when valid, else a short reason (which field is wrong). Pure. */
export function validateCustomVar(def: CustomVarDef): string | null {
  if (!def.name.trim()) return "name";
  if (def.kind === "env") {
    if (!def.envName || !ENV_NAME_RE.test(def.envName)) return "envName";
    return null;
  }
  if (def.kind === "arg") {
    if (!def.arg || !def.arg.trim()) return "arg";
    return null;
  }
  return "kind";
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
