import { getHudState } from "../api";
import { steamOverlay } from "./steamOverlay";

/**
 * Steam's performance-overlay level is what makes mangoapp draw, and only the frontend
 * can change it. When a game applies its own HUD (or the last one did), the level must
 * follow that HUD's on/off so opening the game shows it and closing the game returns to
 * the global one. A user who never gave a game its own HUD is never touched: Steam's
 * level stays theirs.
 */
let engaged = false;

/** Record that a game's own HUD was seen (from the UI), so leaving it restores global. */
export function noteHudScope(ownGameHud: boolean): void {
  if (ownGameHud) engaged = true;
}

export function resetHudGameSyncForTest(): void {
  engaged = false;
}

export async function syncSteamOverlayForGame(): Promise<void> {
  const state = await getHudState();
  const own = state.followsGlobal === false;
  if (!own && !engaged) return;
  engaged = own;
  if (state.model.enabled) await steamOverlay.ensureFullHudVisible();
  else await steamOverlay.ensureHudHidden();
}
