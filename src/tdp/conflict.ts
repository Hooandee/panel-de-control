// Pure conflict logic — no @decky/ui / window reaches, so it stays unit-testable.
// The hook (useTdpConflict) reads Decky globals + RPCs and feeds the results here.

export const SDTDP_NAME = "SimpleDeckyTDP";

/** SimpleDeckyTDP is a rival only when it's installed AND not disabled in Decky. */
export function sdtdpActive(installed: string[], disabled: string[]): boolean {
  return installed.includes(SDTDP_NAME) && !disabled.includes(SDTDP_NAME);
}

export interface ConflictInput {
  sdtdp: boolean;
  hhdManaging: boolean;
  // We only flag a conflict when WE actually manage TDP: hardware supports it and
  // the master switch is on.
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
