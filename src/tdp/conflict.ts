// Pure conflict logic (no window/@decky reaches) so it's unit-testable; the hook
// feeds it the Decky-globals + RPC results.

export const SDTDP_NAME = "SimpleDeckyTDP";

/** SimpleDeckyTDP is a rival only when it's installed AND not disabled in Decky. */
export function sdtdpActive(installed: string[], disabled: string[]): boolean {
  return installed.includes(SDTDP_NAME) && !disabled.includes(SDTDP_NAME);
}

export interface ConflictInput {
  sdtdp: boolean;
  hhdManaging: boolean;
  // Only a conflict when we actually manage TDP (supported + master switch on).
  weControl: boolean;
  tdpSupported: boolean;
}

export interface ConflictResult {
  conflict: boolean;
  rivals: { sdtdp: boolean; hhd: boolean };
}

export function tdpConflict(i: ConflictInput): ConflictResult {
  const rivals = { sdtdp: i.sdtdp, hhd: i.hhdManaging };
  const conflict = i.weControl && i.tdpSupported && (i.sdtdp || i.hhdManaging);
  return { conflict, rivals };
}

/** Monitor-only when the hardware can't do TDP or the master switch is off. */
export function monitorOnly(tdpSupported: boolean, weControl: boolean): boolean {
  return !tdpSupported || !weControl;
}
