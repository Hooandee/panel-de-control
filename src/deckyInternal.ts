// The one place that reaches INTERNAL Decky Loader globals
// (`window.DeckyPluginLoader`, `window.DeckyBackend`) — NOT part of the public
// @decky/api. Centralised so a Decky version that moves them degrades honestly in
// a single spot: an empty list, or a rejected call the caller catches, instead of
// throwing from all over. No @decky/ui import here so pure modules can consume it.

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
 * Call a Decky loader RPC — the same path the Decky UI uses. Rejects if the global
 * is absent or the call throws, so callers decide how to degrade (never fabricate
 * a success).
 */
export async function callBackend(method: string, ...args: unknown[]): Promise<unknown> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const backend = (window as any).DeckyBackend;
  if (typeof backend?.call !== "function") throw new Error("DeckyBackend unavailable");
  return backend.call(method, ...args);
}

/** Make a plugin the active QAM plugin via Decky's loader state. No-op (user lands
 *  on the Decky plugin list) if the setter is gone. */
export function setActivePlugin(name: string): void {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).DeckyPluginLoader?.deckyState?.setActivePlugin?.(name);
  } catch {
    /* land on the Decky plugin list */
  }
}
