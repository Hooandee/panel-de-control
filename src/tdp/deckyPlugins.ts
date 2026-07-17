// Reaches to INTERNAL Decky Loader globals (`window.DeckyPluginLoader`,
// `window.DeckyBackend`) that are NOT part of the public @decky/api. Every one is
// guarded so a Decky version that moved them degrades honestly (empty list / false)
// instead of throwing. Mirrors the pattern in src/system/colores.ts. No @decky/ui
// import here so the values can be consumed without pulling UI into a test path.

function pluginNames(kind: "installedPlugins" | "disabledPlugins"): string[] {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const st = (window as any).DeckyPluginLoader?.deckyState?.publicState?.();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return (st?.[kind] ?? []).map((p: any) => p?.name ?? p);
  } catch {
    return [];
  }
}

/** Names of plugins Decky currently has installed. */
export function installedPlugins(): string[] {
  return pluginNames("installedPlugins");
}

/** Names of plugins the user has disabled in Decky. */
export function disabledPlugins(): string[] {
  return pluginNames("disabledPlugins");
}

/**
 * Disable a plugin via the same loader RPC the Decky UI uses (reversible from
 * Decky). Only reports success once the plugin actually shows up in
 * `disabledPlugins()`. The state may take a tick to update, so a caller that
 * re-reads shortly after will still see the truth.
 */
export async function disablePlugin(name: string): Promise<boolean> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const backend = (window as any).DeckyBackend;
    if (typeof backend?.call !== "function") return false;
    await backend.call("utilities/disable_plugin", name);
    return disabledPlugins().includes(name);
  } catch {
    return false;
  }
}
