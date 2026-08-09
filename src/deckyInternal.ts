import type { ReactNode } from "react";

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

interface DeckyState {
  publicState?(): Partial<Record<"installedPlugins" | "disabledPlugins", PluginListEntry[]>>;
  setActivePlugin?(name: string): void;
}

type PluginListEntry = string | { name?: string };

interface DeckyHost {
  __TABS_HOOK_INSTANCE?: unknown;
  DeckyPluginLoader?: { deckyState?: DeckyState };
  DeckyBackend?: { call?(method: string, ...args: unknown[]): Promise<unknown> };
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
  const hook = (host as DeckyHost | null)?.__TABS_HOOK_INSTANCE as Partial<DeckyTabsHook> | undefined;
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

export function registerQuickAccessTab(
  view: QuickAccessTabView,
  host: unknown = window,
): QuickAccessTabRegistration {
  try {
    const hook = tabsHookOf(host);
    if (!hook) return NO_QAM_TAB;
    if (!removeOwnedQamTabs(hook)) return NO_QAM_TAB;

    const tab: DeckyQuickAccessTab = {
      ...view,
      id: PDC_QAM_TAB_ID,
      __pdcOwner: PDC_QAM_TAB_OWNER,
    };
    try {
      hook.add(tab);
    } catch {
      if (matchingQamTabs(hook).includes(tab)) {
        removeOwnedQamTabs(hook);
      }
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
    const state = (window as unknown as DeckyHost).DeckyPluginLoader?.deckyState?.publicState?.();
    return (state?.[kind] ?? [])
      .map((plugin) => typeof plugin === "string" ? plugin : plugin.name)
      .filter((name): name is string => typeof name === "string");
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

export async function callBackend(method: string, ...args: unknown[]): Promise<unknown> {
  const backend = (window as unknown as DeckyHost).DeckyBackend;
  if (typeof backend?.call !== "function") throw new Error("DeckyBackend unavailable");
  return backend.call(method, ...args);
}

export function setActivePlugin(name: string): void {
  try {
    (window as unknown as DeckyHost).DeckyPluginLoader?.deckyState?.setActivePlugin?.(name);
  } catch {}
}
