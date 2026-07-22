import { createContext, useContext } from "react";
import { TdpControl } from "./useTdp";

// Potencia's core (power arc + slider + presets) and its GPU-clock / Auto‑TDP
// blocks share ONE TDP state through the section provider: scope, live power draw
// and the debounced commits are cross-block state, so a single owner is correct.
export interface PotenciaCtx extends TdpControl {
  /** Another TDP manager owns control — every write control steps aside. */
  monitorOnly: boolean;
  /** The Auto‑TDP module is enabled (editor power toggle). */
  autoTdpEnabled: boolean;
}

const Ctx = createContext<PotenciaCtx | null>(null);
export const PotenciaProvider = Ctx.Provider;

/** The shared Potencia controls. Only valid inside <PotenciaProvider>. */
export function usePotencia(): PotenciaCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("usePotencia outside PotenciaProvider");
  return c;
}
