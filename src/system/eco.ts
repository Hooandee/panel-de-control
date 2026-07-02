// Pure helper for download mode's ambient dim. No React/SteamClient.

/** Screen brightness (%) for the ambient dim: wake level when the user is active,
 *  the low floor when idle. */
export function ecoBrightness(active: boolean, wakePct: number, floorPct: number): number {
  return active ? wakePct : floorPct;
}
