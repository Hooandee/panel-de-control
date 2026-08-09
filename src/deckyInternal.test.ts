import { describe, expect, it } from "vitest";

import {
  PDC_QAM_TAB_ID,
  registerQuickAccessTab,
  removeOwnedQuickAccessTabs,
} from "./deckyInternal";

type FakeTab = Record<string, unknown> & { id: number };

function createHook() {
  const hook = {
    tabs: [{ id: 999 } as FakeTab],
    add(tab: FakeTab) {
      hook.tabs.push(tab);
    },
    removeById(id: number) {
      hook.tabs = hook.tabs.filter((tab) => tab.id !== id);
    },
  };
  return hook;
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
    ];

    for (const host of hosts) {
      const result = registerQuickAccessTab(view, host);
      expect(result.registered).toBe(false);
      expect(() => result.dispose()).not.toThrow();
    }
  });
});
