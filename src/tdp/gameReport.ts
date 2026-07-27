// Pure guard for the persistent game watcher (gameWatcher.ts). Kept free of any
// @decky/ui import so it stays unit-testable.
//
// `inFlight === undefined` means nothing is being sent right now. `null` is a REAL
// target ("no game running"), so it must NOT double as the idle sentinel: when both
// used `null`, a game exit (target=null) matched the idle sentinel and the report was
// swallowed — the backend stayed pinned to the last game and its per-game profile
// leaked into the Global view, with auto-TDP appearing stuck on.
export function shouldReportAppid(
  target: string | null,
  committed: string | null,
  inFlight: string | null | undefined,
): boolean {
  return target !== committed && target !== inFlight;
}
