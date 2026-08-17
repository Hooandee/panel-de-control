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

interface RenderedQuickAccessTab {
  decky?: boolean;
  key: unknown;
}

interface DeckyTabsHook {
  tabs: DeckyQuickAccessTab[];
  add(tab: DeckyQuickAccessTab): void;
  removeById(id: number): void;
  render(existingTabs: RenderedQuickAccessTab[], visible: boolean): void;
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
    || typeof hook.render !== "function"
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

export function quickAccessTabDiagnostics(
  host: unknown = window,
  qamDocument: Document | null = null,
) {
  let hook: { tabs?: unknown } | null = null;
  try {
    const candidate = (host as { __TABS_HOOK_INSTANCE?: unknown } | null)
      ?.__TABS_HOOK_INSTANCE;
    if (candidate && typeof candidate === "object") hook = candidate;
  } catch {}

  const tabs = Array.isArray(hook?.tabs) ? hook.tabs : null;
  const registryIds = tabs?.map((tab) => (
    tab && typeof tab === "object" ? (tab as { id?: unknown }).id : undefined
  )) ?? null;

  let renderedIds: string[] | null = null;
  let roots: Element[] | null = null;
  try {
    if (qamDocument) {
      renderedIds = Array.from(
        qamDocument.querySelectorAll<HTMLElement>("[id^='quickaccess_tab_']"),
        (node) => node.id,
      );
      roots = Array.from(qamDocument.querySelectorAll(".pdc-root"));
    }
  } catch {}

  return {
    hook_available: hook !== null,
    registry_count: registryIds?.length ?? null,
    registry_unique_count: registryIds ? new Set(registryIds).size : null,
    registry_decky_count: registryIds?.filter((id) => id === DECKY_PLUGIN_TAB_ID).length ?? null,
    registry_pdc_count: registryIds?.filter((id) => id === PDC_QAM_TAB_ID).length ?? null,
    qam_document_available: qamDocument !== null,
    qam_document_hidden: qamDocument?.hidden ?? null,
    rendered_count: renderedIds?.length ?? null,
    rendered_unique_count: renderedIds ? new Set(renderedIds).size : null,
    rendered_decky_count:
      renderedIds?.filter((id) => id === `quickaccess_tab_${DECKY_PLUGIN_TAB_ID}`).length ?? null,
    rendered_pdc_count:
      renderedIds?.filter((id) => id === `quickaccess_tab_${PDC_QAM_TAB_ID}`).length ?? null,
    panel_root_count: roots?.length ?? null,
    visible_panel_root_count: roots?.filter((node) => {
      const rect = node.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }).length ?? null,
  };
}

function reconcilesTabsExactly(
  hook: DeckyTabsHook,
  desiredTabs: DeckyQuickAccessTab[],
): boolean {
  const nativeTab = Object.freeze({ key: "pdc-native-probe" });
  const renderedTabs: RenderedQuickAccessTab[] = [
    nativeTab,
    ...hook.tabs.map((tab) => ({ decky: true, key: tab.id })),
  ];
  const probeTabs = desiredTabs.map((tab) => Object.freeze({ ...tab }));
  if (new Set(probeTabs.map((tab) => tab.id)).size !== probeTabs.length) return false;

  const probeHook = Object.create(hook) as DeckyTabsHook;
  Object.defineProperty(probeHook, "tabs", { value: Object.freeze(probeTabs) });
  hook.render.call(probeHook, renderedTabs, false);

  return renderedTabs.length === probeTabs.length + 1
    && renderedTabs[0] === nativeTab
    && renderedTabs.slice(1).every((tab, index) => (
      tab.decky === true && tab.key === probeTabs[index].id
    ));
}

function removeOwnedQamTabs(hook: DeckyTabsHook): boolean {
  const matching = matchingQamTabs(hook);
  if (matching.some((tab) => !ownsQamTab(tab))) return false;
  if (matching.length > 0) {
    const remaining = hook.tabs.filter((tab) => tab.id !== PDC_QAM_TAB_ID);
    if (!reconcilesTabsExactly(hook, remaining)) return false;
    hook.removeById(PDC_QAM_TAB_ID);
  }
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
    if (!reconcilesTabsExactly(hook, [...hook.tabs, tab])) return NO_QAM_TAB;
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
          if (matchingQamTabs(hook).includes(tab)) removeOwnedQamTabs(hook);
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

export async function callBackend(method: string, ...args: unknown[]): Promise<unknown> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const backend = (window as any).DeckyBackend;
  if (typeof backend?.call !== "function") throw new Error("DeckyBackend unavailable");
  return backend.call(method, ...args);
}

export function setActivePlugin(name: string): void {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).DeckyPluginLoader?.deckyState?.setActivePlugin?.(name);
  } catch {}
}
