import { TdpControl } from "./useTdp";
import { createSectionContext } from "../sectionContext";

// Potencia's core (power arc + slider + presets) and its GPU-clock / Auto‑TDP
// blocks share ONE TDP state through the section provider: scope, live power draw
// and the debounced commits are cross-block state, so a single owner is correct.
export interface PotenciaCtx extends TdpControl {
  /** Another TDP manager owns control — every write control steps aside. */
  monitorOnly: boolean;
  /** The Auto‑TDP module is enabled (editor power toggle). */
  autoTdpEnabled: boolean;
}

export const [PotenciaProvider, usePotencia] = createSectionContext<PotenciaCtx>("usePotencia");
