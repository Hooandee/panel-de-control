import { TdpControl } from "./useTdp";
import { createSectionContext } from "../sectionContext";

export interface PotenciaCtx extends TdpControl {
  monitorOnly: boolean;
  autoTdpEnabled: boolean;
  // Turn the TDP master switch back on. Resolves when the write settles.
  onReactivate: () => Promise<void>;
}

export const [PotenciaProvider, usePotencia] = createSectionContext<PotenciaCtx>("usePotencia");
