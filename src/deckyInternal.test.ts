import { describe, expect, it } from "vitest";

import {
  PDC_QAM_TAB_ID,
  quickAccessTabDiagnostics,
  registerQuickAccessTab,
  removeOwnedQuickAccessTabs,
} from "./deckyInternal";

type FakeTab = Record<string, unknown> & { id: number };
type RenderedTab = Record<string, unknown> & { decky?: boolean; key: number | string };

function createHook() {
  const hook = {
    tabs: [{ id: 999 } as FakeTab],
    add(tab: FakeTab) {
      hook.tabs.push(tab);
    },
    removeById(id: number) {
      hook.tabs = hook.tabs.filter((tab) => tab.id !== id);
    },
    render(this: { tabs: FakeTab[] }, existingTabs: RenderedTab[]) {
      const nativeTabs = existingTabs.filter((tab) => !tab.decky);
      existingTabs.splice(
        0,
        existingTabs.length,
        ...nativeTabs,
        ...this.tabs.map((tab) => ({ decky: true, key: tab.id })),
      );
    },
  };
  return hook;
}

function appendRegistryOnCountChange(
  this: { tabs: FakeTab[] },
  existingTabs: RenderedTab[],
) {
  const deckyTabCount = existingTabs.filter((tab) => tab.decky).length;
  if (deckyTabCount === this.tabs.length) return;
  existingTabs.push(...this.tabs.map((tab) => ({ decky: true, key: tab.id })));
}

describe("registerQuickAccessTab", () => {
  it("falls back when Decky's tab hook is absent", () => {
    const result = registerQuickAccessTab(
      { title: null, content: "panel", icon: "icon" },
      {},
    );

    expect(result.registered).toBe(false);
    expect(() => result.dispose()).not.toThrow();
  });

  it("registers and disposes exactly its own QAM tab", () => {
    const hook = createHook();
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(true);
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(1);

    result.dispose();
    result.dispose();

    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(0);
  });

  it("falls back when Decky appends the full registry after a tab count change", () => {
    const hook = createHook();
    hook.render = appendRegistryOnCountChange;

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(hook.tabs.map((tab) => tab.id)).toEqual([999]);
  });

  it("does not remove a registered tab if Decky stops reconciling exactly", () => {
    const hook = createHook();
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );
    hook.render = appendRegistryOnCountChange;

    result.dispose();

    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(1);
  });

  it("replaces its stale registration without allowing the stale disposer to remove the new one", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    const stale = registerQuickAccessTab(
      { title: "Old", content: "old panel", icon: "old icon" },
      host,
    );
    const current = registerQuickAccessTab(
      { title: "Current", content: "current panel", icon: "current icon" },
      host,
    );

    expect(stale.registered).toBe(true);
    expect(current.registered).toBe(true);
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(1);

    stale.dispose();
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(1);

    current.dispose();
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(0);
  });

  it("removes an owned tab left behind by an earlier loader session", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    registerQuickAccessTab(
      { title: "Old", content: "old panel", icon: "old icon" },
      host,
    );

    const removed = removeOwnedQuickAccessTabs(host);

    expect(removed).toBe(true);
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(0);
  });

  it("preserves a colliding tab that it does not own", () => {
    const hook = createHook();
    const collision = { id: PDC_QAM_TAB_ID, title: "Other extension" } as FakeTab;
    hook.tabs.push(collision);

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toEqual([collision]);
  });

  it("does not touch a replacement global hook during disposal", () => {
    const original = createHook();
    const replacement = createHook();
    const host = { __TABS_HOOK_INSTANCE: original };
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );

    host.__TABS_HOOK_INSTANCE = replacement;
    result.dispose();

    expect(original.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(0);
    expect(replacement.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(0);
  });

  it("removes its partial registration when add throws", () => {
    const hook = createHook();
    hook.add = (tab: FakeTab) => {
      hook.tabs.push(tab);
      throw new Error("Decky render failed");
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(0);
  });

  it("falls back when add does not append the exact tab", () => {
    const hook = createHook();
    hook.add = () => {};

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(0);
  });

  it("rejects and removes duplicate owned tabs produced by add", () => {
    const hook = createHook();
    hook.add = (tab: FakeTab) => {
      hook.tabs.push(tab, tab);
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(0);
  });

  it("disposes all owned duplicates while the captured registration is still present", () => {
    const hook = createHook();
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );
    const registered = hook.tabs.find((tab) => tab.id === PDC_QAM_TAB_ID)!;
    hook.tabs.push({ ...registered });

    result.dispose();

    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(0);
  });

  it("falls back when the Decky tab or required hook capabilities are missing", () => {
    const view = { title: "Panel de Control", content: "panel", icon: "icon" };
    const withoutDecky = createHook();
    withoutDecky.tabs = [];

    const hosts = [
      { __TABS_HOOK_INSTANCE: withoutDecky },
      { __TABS_HOOK_INSTANCE: { tabs: [{ id: 999 }], removeById() {} } },
      { __TABS_HOOK_INSTANCE: { tabs: [{ id: 999 }], add() {} } },
      { __TABS_HOOK_INSTANCE: { tabs: [{ id: 999 }], add() {}, removeById() {} } },
    ];

    for (const host of hosts) {
      const result = registerQuickAccessTab(view, host);
      expect(result.registered).toBe(false);
      expect(() => result.dispose()).not.toThrow();
    }
  });
});

describe("quickAccessTabDiagnostics", () => {
  it("uses null counts when QAM internals are unavailable", () => {
    expect(quickAccessTabDiagnostics({}, null)).toEqual({
      hook_available: false,
      registry_count: null,
      registry_unique_count: null,
      registry_decky_count: null,
      registry_pdc_count: null,
      qam_document_available: false,
      qam_document_hidden: null,
      rendered_count: null,
      rendered_unique_count: null,
      rendered_decky_count: null,
      rendered_pdc_count: null,
      panel_root_count: null,
      visible_panel_root_count: null,
    });
  });

  it("reports bounded QAM counts without exposing tab identifiers", () => {
    const host = {
      __TABS_HOOK_INSTANCE: {
        tabs: [{ id: 999 }, { id: PDC_QAM_TAB_ID }, { id: PDC_QAM_TAB_ID }],
      },
    };
    const visibleRoot = { getBoundingClientRect: () => ({ width: 320, height: 600 }) };
    const hiddenRoot = { getBoundingClientRect: () => ({ width: 0, height: 0 }) };
    const doc = {
      hidden: false,
      querySelectorAll(selector: string) {
        if (selector === ".pdc-root") return [visibleRoot, hiddenRoot];
        return [
          { id: "quickaccess_tab_0" },
          { id: "quickaccess_tab_999" },
          { id: "quickaccess_tab_999" },
          { id: `quickaccess_tab_${PDC_QAM_TAB_ID}` },
        ];
      },
    };

    expect(quickAccessTabDiagnostics(host, doc as unknown as Document)).toEqual({
      hook_available: true,
      registry_count: 3,
      registry_unique_count: 2,
      registry_decky_count: 1,
      registry_pdc_count: 2,
      qam_document_available: true,
      qam_document_hidden: false,
      rendered_count: 4,
      rendered_unique_count: 3,
      rendered_decky_count: 2,
      rendered_pdc_count: 1,
      panel_root_count: 2,
      visible_panel_root_count: 1,
    });
  });
});
