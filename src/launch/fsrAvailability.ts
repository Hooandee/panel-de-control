import { CATALOG, pillVisible } from "./catalog";
import { GpuGen } from "./proton";
import { ProtonCapabilityState } from "./useProtonCapabilities";

export function fsrUnavailableReason(gpu: GpuGen, capabilities: ProtonCapabilityState): string | undefined {
  if (gpu !== "rdna3" && gpu !== "rdna4") return undefined;
  if (capabilities.status !== "ready") return `params.fsr4.${capabilities.status}`;
  if (CATALOG.some((pill) => pill.exclusiveGroup === "fsr4-upgrade" && pillVisible(pill, capabilities.envs, gpu))) return undefined;
  return "params.fsr4.unsupported";
}
