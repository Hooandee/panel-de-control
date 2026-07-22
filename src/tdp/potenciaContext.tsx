import { TdpControl } from "./useTdp";
import { createSectionContext } from "../sectionContext";

export interface PotenciaCtx extends TdpControl {
  monitorOnly: boolean;
  autoTdpEnabled: boolean;
}

export const [PotenciaProvider, usePotencia] = createSectionContext<PotenciaCtx>("usePotencia");
