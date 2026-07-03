import type { DeviceInfo } from "../api";

// The sibling RGB plugin we integrate with. `name` must match its plugin.json
// `name` exactly (that's the key Decky uses in its plugin list + setActivePlugin).
export const COLORES_PLUGIN_NAME = "Colores";
// Install artifact: the latest GitHub release zip (release-please publishes it as
// "<name>.zip"). Same "install from URL" the Decky store uses under the hood.
export const COLORES_RELEASE_URL =
  "https://github.com/Hooandee/decky-colores/releases/latest/download/Colores.zip";

export type ColoresPhase = "idle" | "installing" | "error";
export type ColoresCardState = "hidden" | "install" | "installing" | "open" | "error";

/**
 * Steam Deck has no RGB LEDs → no lighting card. Every other detected handheld
 * (or the generic fallback) may have them, so we offer the integration. Pure so
 * the section can gate on it and it stays unit-tested.
 */
export function deviceHasRgb(device: DeviceInfo | null): boolean {
  if (!device) return false;
  return !device.key.startsWith("steam_deck");
}

/** Pure resolver: which visual state the card renders in. */
export function coloresCardState(input: {
  hasRgb: boolean;
  installed: boolean;
  phase: ColoresPhase;
}): ColoresCardState {
  if (!input.hasRgb) return "hidden";
  if (input.phase === "installing") return "installing";
  if (input.phase === "error") return "error";
  return input.installed ? "open" : "install";
}

// ── Decky-internal adapters ────────────────────────────────────────────────
// These reach INTERNAL Decky Loader globals (`window.DeckyPluginLoader`,
// `window.DeckyBackend`) that are NOT part of the public `@decky/api`. Every one
// is guarded so a Decky version that moved them degrades honestly (never-fake:
// we report "not installed" / fall back to the store rather than throw or lie).

/** Reads Decky's in-memory installed-plugin list to see if Colores is present. */
export function isColoresInstalled(): boolean {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const loader = (window as any).DeckyPluginLoader;
    const plugins = loader?.deckyState?.publicState?.().installedPlugins ?? [];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return plugins.some((p: any) => p?.name === COLORES_PLUGIN_NAME);
  } catch {
    return false;
  }
}

/**
 * Installs Colores from its GitHub release via the same loader RPC the store
 * uses (`utilities/install_plugin`, artifact + name; the backend defaults
 * version/hash/install-type). Resolves to whether the RPC completed. Never throws.
 */
export async function installColores(): Promise<boolean> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const backend = (window as any).DeckyBackend;
    if (typeof backend?.call !== "function") return false;
    await backend.call("utilities/install_plugin", COLORES_RELEASE_URL, COLORES_PLUGIN_NAME);
    return true;
  } catch {
    return false;
  }
}

/** Makes Colores the active QAM plugin via Decky's loader state. Internal API —
 *  no-op (user lands on the Decky plugin list) if the setter is gone. Kept here
 *  with its sibling reaches so all internal-global access lives in one file. */
export function setActiveColoresPlugin(): void {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).DeckyPluginLoader?.deckyState?.setActivePlugin?.(COLORES_PLUGIN_NAME);
  } catch {
    /* land on the Decky plugin list */
  }
}

/**
 * After an install RPC resolves, Decky needs a moment to register + load the new
 * plugin into its state. Poll a few times so we only flip to "installed" once it
 * REALLY appears (never-fake).
 */
export async function waitForColoresInstalled(tries = 8, gapMs = 800): Promise<boolean> {
  for (let i = 0; i < tries; i++) {
    if (isColoresInstalled()) return true;
    await new Promise((r) => setTimeout(r, gapMs));
  }
  return isColoresInstalled();
}
