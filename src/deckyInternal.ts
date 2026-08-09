import type { ReactNode } from "react";

// The one place that reaches INTERNAL Decky Loader globals
// (`window.DeckyPluginLoader`, `window.DeckyBackend`) — NOT part of @decky/api.
// Centralised + guarded so a Decky version that moves them degrades in one spot.
// No @decky/ui import here so pure modules can consume it.

export const PDC_QAM_TAB_ID = 0x504443;

const PDC_QAM_TAB_OWNER = "panel-de-control";
const DECKY_PLUGIN_TAB_ID = 999;

interface QuickAccessTabView {
  title: ReactNode;
  content: ReactNode;
  icon: ReactNode;
}

interface DeckyQuickAccessTab extends QuickAccessTabView {
  id: number;
  __pdcOwner?: string;
}

interface DeckyTabsHook {
  tabs: DeckyQuickAccessTab[];
  add(tab: DeckyQuickAccessTab): void;
  removeById(id: number): void;
}

export interface QuickAccessTabRegistration {
  registered: boolean;
  dispose(): void;
}

const NO_QAM_TAB: QuickAccessTabRegistration = {
  registered: false,
  dispose() {},
};

function tabsHookOf(host: unknown): DeckyTabsHook | null {
  const hook = (host as { __TABS_HOOK_INSTANCE?: unknown } | null)
    ?.__TABS_HOOK_INSTANCE as Partial<DeckyTabsHook> | undefined;
  if (
    !hook
    || !Array.isArray(hook.tabs)
    || typeof hook.add !== "function"
    || typeof hook.removeById !== "function"
    || !hook.tabs.some((tab) => tab?.id === DECKY_PLUGIN_TAB_ID)
  ) {
    return null;
  }
  return hook as DeckyTabsHook;
}

function matchingQamTabs(hook: DeckyTabsHook): DeckyQuickAccessTab[] {
  return hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID);
}

function ownsQamTab(tab: DeckyQuickAccessTab): boolean {
  return tab.__pdcOwner === PDC_QAM_TAB_OWNER;
}

function removeOwnedQamTabs(hook: DeckyTabsHook): boolean {
  const matching = matchingQamTabs(hook);
  if (matching.some((tab) => !ownsQamTab(tab))) return false;
  if (matching.length > 0) hook.removeById(PDC_QAM_TAB_ID);
  return matchingQamTabs(hook).length === 0;
}

export function removeOwnedQuickAccessTabs(host: unknown = window): boolean {
  try {
    const hook = tabsHookOf(host);
    return hook ? removeOwnedQamTabs(hook) : false;
  } catch {
    return false;
  }
}

export function registerQuickAccessTab(
  view: QuickAccessTabView,
  host: unknown = window,
): QuickAccessTabRegistration {
  try {
    const hook = tabsHookOf(host);
    if (!hook || !removeOwnedQamTabs(hook)) return NO_QAM_TAB;

    const tab: DeckyQuickAccessTab = {
      ...view,
      id: PDC_QAM_TAB_ID,
      __pdcOwner: PDC_QAM_TAB_OWNER,
    };
    try {
      hook.add(tab);
    } catch {
      if (matchingQamTabs(hook).includes(tab)) removeOwnedQamTabs(hook);
      return NO_QAM_TAB;
    }
    const added = matchingQamTabs(hook);
    if (added.length !== 1 || added[0] !== tab) {
      removeOwnedQamTabs(hook);
      return NO_QAM_TAB;
    }

    let disposed = false;
    return {
      registered: true,
      dispose() {
        if (disposed) return;
        disposed = true;
        try {
          const matching = matchingQamTabs(hook);
          if (matching.includes(tab) && matching.every(ownsQamTab)) {
            hook.removeById(PDC_QAM_TAB_ID);
          }
        } catch {}
      },
    };
  } catch {
    return NO_QAM_TAB;
  }
}

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
