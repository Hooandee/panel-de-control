import type { Scope } from "./api";

/**
 * The scope tab a section shows for the running game: its OWN profile only when it has
 * an active per-game one, otherwise global (also global when no game runs). Pure (no
 * React) so it can be unit-tested; useScopeSync wires it to React + the section's RPC.
 */
export function scopeFor(appid: string | null | undefined, followsGlobal: boolean | undefined): Scope {
  return appid && !followsGlobal ? "game" : "global";
}
