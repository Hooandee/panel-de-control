// Panel reads Steam's globals as bare identifiers (`SteamClient?.X`), which throws a
// ReferenceError when the binding does not exist. Outside Steam they exist and are empty,
// so every existing guard reports "unavailable" instead of crashing.
export const STEAM_GLOBALS = [
  "SteamClient",
  "appStore",
  "appDetailsStore",
  "SteamUIStore",
  "collectionStore",
  "DeckyBackend",
  "DeckyPluginLoader",
  "DFL",
  "FocusNavController",
] as const;

export function declareSteamGlobals(target: Record<string, unknown> = globalThis as Record<string, unknown>): void {
  for (const name of STEAM_GLOBALS) {
    if (!(name in target)) target[name] = undefined;
  }
}
