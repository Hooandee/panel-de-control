// The one place that reaches INTERNAL Decky Loader globals
// (`window.DeckyPluginLoader`, `window.DeckyBackend`) — NOT part of @decky/api.
// Centralised + guarded so a Decky version that moves them degrades in one spot.
// No @decky/ui import here so pure modules can consume it.

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

export function installedPlugins(): string[] {
  return pluginNames("installedPlugins");
}

export function disabledPlugins(): string[] {
  return pluginNames("disabledPlugins");
}

// Rejects if the global is absent or the call throws, so callers decide how to degrade.
export async function callBackend(method: string, ...args: unknown[]): Promise<unknown> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const backend = (window as any).DeckyBackend;
  if (typeof backend?.call !== "function") throw new Error("DeckyBackend unavailable");
  return backend.call(method, ...args);
}

// Make a plugin the active QAM plugin. No-op (user lands on the Decky plugin list)
// if the setter is gone.
export function setActivePlugin(name: string): void {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).DeckyPluginLoader?.deckyState?.setActivePlugin?.(name);
  } catch {
    /* land on the Decky plugin list */
  }
}
