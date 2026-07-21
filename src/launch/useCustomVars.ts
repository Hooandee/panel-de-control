import { useCallback, useEffect, useMemo, useState } from "react";

import { getCustomLaunchVars, setCustomLaunchVars, CustomVarDef } from "../api";
import { Pill } from "./catalog";
import { customVarToPill } from "./customVars";

export interface CustomVarsApi {
  /** The library (null while loading). */
  vars: CustomVarDef[] | null;
  /** The load failed — do NOT treat as empty (adding one would wipe the real list). */
  error: boolean;
  /** The library as catalog pills (empty while loading). */
  pills: Pill[];
  /** Replace the whole library; optimistic, then adopts the coerced result. */
  save: (next: CustomVarDef[]) => void;
  newId: () => string;
}

function makeId(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  return c?.randomUUID ? c.randomUUID() : `${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
}

/** The user's reusable launch-variable library (global). Durable via the backend
 *  SettingsStore — localStorage doesn't survive a CEF reboot. */
export function useCustomVars(): CustomVarsApi {
  const [vars, setVars] = useState<CustomVarDef[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCustomLaunchVars()
      .then((v) => {
        if (cancelled) return;
        setVars(v);
        setError(false);
      })
      // A failed load must NOT read as an empty library: if the user then adds a
      // variable we'd persist [new] and wipe whatever the backend really had.
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const save = useCallback((next: CustomVarDef[]) => {
    setVars(next); // optimistic
    setCustomLaunchVars(next)
      .then((stored) => setVars(stored)) // adopt what the backend actually stored
      .catch(() => setError(true));
  }, []);

  const pills = useMemo(() => (vars ?? []).map(customVarToPill), [vars]);

  return { vars, error, pills, save, newId: makeId };
}
