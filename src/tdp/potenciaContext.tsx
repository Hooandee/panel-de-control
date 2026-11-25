import { TdpControl } from "./useTdp";
import { createSectionContext } from "../sectionContext";

export interface PotenciaCtx extends TdpControl {
  monitorOnly: boolean;
  autoTdpEnabled: boolean;
  // Turn the TDP master switch back on. Resolves when the write settles.
  onReactivate: () => Promise<void>;
  // SteamOS Manager is running: with Panel's control off, Steam is the one driving the TDP.
  steamOsManagerActive: boolean;
  // Hand the TDP back to Steam (turns the master switch off); reversible via onReactivate.
  onReleaseControl: () => Promise<void>;
}

export const [PotenciaProvider, usePotencia] = createSectionContext<PotenciaCtx>("usePotencia");
