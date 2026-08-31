import { describe, expect, it, vi } from "vitest";

import {
  callLegacyPluginBackend,
  callPluginBackend,
  cleanupOwnedQuickAccessTabs,
  PDC_QAM_TAB_ID,
  pluginInventory,
  quickAccessTabDiagnostics,
  registerQuickAccessTab,
  strictPluginInventory,
} from "./deckyInternal";

type FakeTab = Record<string, unknown> & { id: number };
type RenderedTab = Record<string, unknown> & {
  decky?: boolean;
  key: number | string;
  panel?: unknown;
};

function createHook() {
  const hook = {
    tabs: [{ id: 999 } as FakeTab],
    add(tab: FakeTab) {
      hook.tabs.push(tab);
    },
    removeById(id: number) {
      hook.tabs = hook.tabs.filter((tab) => tab.id !== id);
    },
    render(this: { tabs: FakeTab[] }, existingTabs: RenderedTab[], _visible?: boolean) {
      const nativeTabs = existingTabs.filter((tab) => !tab.decky);
      existingTabs.splice(
        0,
        existingTabs.length,
        ...nativeTabs,
        ...this.tabs.map((tab) => ({ decky: true, key: tab.id, panel: tab.content ?? "panel" })),
      );
    },
  };
  return hook;
}

function appendRegistryOnCountChange(
  this: { tabs: FakeTab[] },
  existingTabs: RenderedTab[],
  _visible?: boolean,
) {
  const deckyTabCount = existingTabs.filter((tab) => tab.decky).length;
  if (deckyTabCount === this.tabs.length) return;
  existingTabs.push(...this.tabs.map((tab) => ({
    decky: true,
    key: tab.id,
    panel: tab.content ?? "panel",
  })));
}

function useInheritedRenderer(
  hook: ReturnType<typeof createHook>,
  render: typeof hook.render,
): void {
  Object.setPrototypeOf(hook, { render });
  delete (hook as Partial<typeof hook>).render;
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

  it("adapts Decky's count renderer without remounting existing tabs", () => {
    const hook = createHook();
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const originalRender = hook.render;
    const nativeTab = { key: "native" };
    const standardDeckyTab = { decky: true, key: 999, panel: {} };
    const renderedTabs = [nativeTab, standardDeckyTab];

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(true);
    expect(hook.render).not.toBe(originalRender);

    hook.render(renderedTabs, true);

    expect(renderedTabs.map((tab) => tab.key)).toEqual(["native", 999, PDC_QAM_TAB_ID]);
    expect(renderedTabs[0]).toBe(nativeTab);
    expect(renderedTabs[1]).toBe(standardDeckyTab);

    result.dispose();
    hook.render(renderedTabs, false);

    expect(renderedTabs.map((tab) => tab.key)).toEqual(["native", 999]);
    expect(renderedTabs[1]).toBe(standardDeckyTab);
    expect(hook.render).toBe(originalRender);
  });

  it("renders Decky and the shortcut once when QAM has only native tabs", () => {
    const hook = createHook();
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const nativeTab = Object.freeze({ key: "native" });
    const renderedTabs = [nativeTab];
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    hook.render(renderedTabs, true);

    expect(result.registered).toBe(true);
    expect(renderedTabs.map((tab) => tab.key)).toEqual(["native", 999, PDC_QAM_TAB_ID]);
    expect(renderedTabs[0]).toBe(nativeTab);
  });

  it("preserves other Decky tabs while reconciling the direct shortcut", () => {
    const hook = createHook();
    hook.tabs.push({ id: 321 } as FakeTab);
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const standardDeckyTab = { decky: true, key: 999, panel: {} };
    const otherDeckyTab = { decky: true, key: 321, panel: {} };
    const renderedTabs = [{ key: "native" }, standardDeckyTab, otherDeckyTab];

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );
    hook.render(renderedTabs, true);

    expect(result.registered).toBe(true);
    expect(renderedTabs.map((tab) => tab.key)).toEqual([
      "native",
      999,
      321,
      PDC_QAM_TAB_ID,
    ]);
    expect(renderedTabs[1]).toBe(standardDeckyTab);
    expect(renderedTabs[2]).toBe(otherDeckyTab);
  });

  it("keeps separate shortcut panels for Browser and Embedded QAM arrays", () => {
    const hook = createHook();
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const originalRender = hook.render;
    const browserTabs = [{ key: "browser-native" }, { decky: true, key: 999, panel: {} }];
    const embeddedTabs = [{ key: "embedded-native" }, { decky: true, key: 999, panel: {} }];
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    hook.render(browserTabs, true);
    hook.render(embeddedTabs, false);

    expect(browserTabs[2]).not.toBe(embeddedTabs[2]);
    expect(browserTabs.map((tab) => tab.key)).toEqual(["browser-native", 999, PDC_QAM_TAB_ID]);
    expect(embeddedTabs.map((tab) => tab.key)).toEqual(["embedded-native", 999, PDC_QAM_TAB_ID]);

    result.dispose();

    expect(browserTabs.map((tab) => tab.key)).toEqual(["browser-native", 999]);
    expect(embeddedTabs.map((tab) => tab.key)).toEqual(["embedded-native", 999]);
    expect(hook.render).toBe(originalRender);
  });

  it("preserves each QAM array's last visibility during synchronous cleanup", () => {
    const hook = createHook();
    const setStandardVisibility = vi.fn();
    useInheritedRenderer(hook, function (
      this: { tabs: FakeTab[] },
      tabs: RenderedTab[],
      visible?: boolean,
    ) {
      appendRegistryOnCountChange.call(this, tabs);
      for (const tab of tabs) {
        (tab.qAMVisibilitySetter as ((next: boolean) => void) | undefined)?.(!!visible);
      }
    });
    const renderedTabs = [
      { key: "native" },
      {
        decky: true,
        key: 999,
        panel: {},
        qAMVisibilitySetter: setStandardVisibility,
      },
    ];
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );
    hook.render(renderedTabs, true);

    result.dispose();

    expect(setStandardVisibility).toHaveBeenLastCalledWith(true);
  });

  it("does not remount stable tabs across repeated renders", () => {
    const hook = createHook();
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const nativeTab = Object.freeze({ key: "native" });
    const standardDeckyTab = { decky: true, key: 999, panel: {} };
    const renderedTabs = [nativeTab, standardDeckyTab];
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );
    hook.render(renderedTabs, true);
    const directTab = renderedTabs[2];

    for (let index = 0; index < 100; index += 1) hook.render(renderedTabs, index % 2 === 0);

    expect(renderedTabs[0]).toBe(nativeTab);
    expect(renderedTabs[1]).toBe(standardDeckyTab);
    expect(renderedTabs[2]).toBe(directTab);
  });

  it("refreshes only its own rendered tab after a plugin reload", () => {
    const hook = createHook();
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const host = { __TABS_HOOK_INSTANCE: hook };
    const standardDeckyTab = { decky: true, key: 999, panel: {} };
    const renderedTabs = [{ key: "native" }, standardDeckyTab];
    registerQuickAccessTab(
      { title: "Old", content: "old panel", icon: "old icon" },
      host,
    );
    hook.render(renderedTabs, true);
    const oldDirectTab = renderedTabs[2];

    registerQuickAccessTab(
      { title: "Current", content: "current panel", icon: "current icon" },
      host,
    );
    hook.render(renderedTabs, true);

    expect(renderedTabs[1]).toBe(standardDeckyTab);
    expect(renderedTabs[2]).not.toBe(oldDirectTab);
  });

  it("fails closed when the reused QAM array is already contaminated", () => {
    const hook = createHook();
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const host = { __TABS_HOOK_INSTANCE: hook };
    const renderedTabs = [
      { key: "native" },
      { decky: true, key: 999 },
      { decky: true, key: "999" },
    ];
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );

    expect(() => hook.render(renderedTabs, true)).not.toThrow();
    expect(renderedTabs.map((tab) => tab.key)).toEqual(["native", 999, "999"]);
    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
  });

  it("keeps the first runtime failure sticky and reports it once", () => {
    const hook = createHook();
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const host = { __TABS_HOOK_INSTANCE: hook };
    const renderedTabs = [{ key: "native" }, { decky: true, key: 999, panel: {} }];
    const onRuntimeFailure = vi.fn();
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
      onRuntimeFailure,
    );
    hook.render(renderedTabs, true);
    renderedTabs.push({ decky: true, key: 999, panel: {} });

    hook.render(renderedTabs, true);
    renderedTabs.pop();
    const afterFailure = [...renderedTabs];
    hook.render(renderedTabs, true);

    expect(onRuntimeFailure).toHaveBeenCalledOnce();
    expect(renderedTabs).toEqual(afterFailure);
    expect(quickAccessTabDiagnostics(host).render_adapter_failure)
      .toBe("rendered_registry_mismatch");
  });

  it("does not report registration success when add triggers a failing render", () => {
    const hook = createHook();
    const renderedTabs = [{ key: "native" }, { decky: true, key: 999, panel: {} }];
    useInheritedRenderer(hook, function (
      this: { tabs: FakeTab[] },
      tabs: RenderedTab[],
      visible?: boolean,
    ) {
      if (visible) throw new Error("visible renderer failed");
      appendRegistryOnCountChange.call(this, tabs);
    });
    hook.add = (tab: FakeTab) => {
      hook.tabs.push(tab);
      hook.render(renderedTabs, true);
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.restartRequired).toBe(true);
    expect(result.reason).toBe("add_failed");
  });

  it("does not wrap an unknown renderer already assigned on the hook", () => {
    const hook = createHook();
    hook.render = appendRegistryOnCountChange;
    const originalRender = hook.render;

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(hook.render).toBe(originalRender);
    expect(hook.tabs.map((tab) => tab.id)).toEqual([999]);
  });

  it("falls back when Decky cannot generate a valid shortcut panel", () => {
    const hook = createHook();
    useInheritedRenderer(hook, function (this: { tabs: FakeTab[] }, tabs: RenderedTab[]) {
      if (tabs.filter((tab) => tab.decky).length === this.tabs.length) return;
      tabs.push(...this.tabs.map((tab) => ({ decky: true, key: tab.id })));
    });
    const originalRender = hook.render;

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(hook.render).toBe(originalRender);
    expect(hook.tabs.map((tab) => tab.id)).toEqual([999]);
  });

  it("rolls back the real array when Decky's renderer throws at runtime", () => {
    const hook = createHook();
    let fail = false;
    useInheritedRenderer(hook, function (this: { tabs: FakeTab[] }, tabs: RenderedTab[]) {
      if (fail) {
        tabs.push({ decky: true, key: 123, panel: {} });
        throw new Error("runtime failure");
      }
      appendRegistryOnCountChange.call(this, tabs);
    });
    const host = { __TABS_HOOK_INSTANCE: hook };
    const nativeTab = { key: "native" };
    const renderedTabs = [nativeTab];
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    fail = true;

    expect(() => hook.render(renderedTabs, true)).not.toThrow();
    expect(renderedTabs).toEqual([nativeTab]);
    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
  });

  it("fails closed on renderer re-entry without recursing", () => {
    const hook = createHook();
    let reenter = false;
    useInheritedRenderer(hook, function (this: ReturnType<typeof createHook>, tabs: RenderedTab[]) {
      if (reenter) return this.render(tabs, true);
      appendRegistryOnCountChange.call(this, tabs);
    });
    const host = { __TABS_HOOK_INSTANCE: hook };
    const renderedTabs = [{ key: "native" }];
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    reenter = true;

    expect(() => hook.render(renderedTabs, true)).not.toThrow();
    expect(renderedTabs.map((tab) => tab.key)).toEqual(["native"]);
    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
  });

  it("reconciles a third-party registry addition without remounting stable tabs", () => {
    const hook = createHook();
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const host = { __TABS_HOOK_INSTANCE: hook };
    const renderedTabs = [{ key: "native" }, { decky: true, key: 999, panel: {} }];
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    hook.render(renderedTabs, true);
    const before = [...renderedTabs];
    hook.tabs.push({ id: 321 } as FakeTab);

    expect(() => hook.render(renderedTabs, true)).not.toThrow();
    expect(renderedTabs.map((tab) => tab.key)).toEqual([
      "native",
      999,
      PDC_QAM_TAB_ID,
      321,
    ]);
    expect(renderedTabs[0]).toBe(before[0]);
    expect(renderedTabs[1]).toBe(before[1]);
    expect(renderedTabs[2]).toBe(before[2]);
    expect(cleanupOwnedQuickAccessTabs(host)).toBe(false);
  });

  it("reconciles third-party removal and replacement without remounting other tabs", () => {
    const hook = createHook();
    const thirdParty = { id: 321, content: "old" } as FakeTab;
    hook.tabs.push(thirdParty);
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const standard = { decky: true, key: 999, panel: {} };
    const thirdPartyRendered = { decky: true, key: 321, panel: {} };
    const renderedTabs = [{ key: "native" }, standard, thirdPartyRendered];
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );
    hook.render(renderedTabs, true);
    const direct = renderedTabs[3];

    hook.tabs = hook.tabs.filter((tab) => tab.id !== 321);
    hook.render(renderedTabs, true);

    expect(renderedTabs.map((tab) => tab.key)).toEqual(["native", 999, PDC_QAM_TAB_ID]);
    expect(renderedTabs[1]).toBe(standard);
    expect(renderedTabs[2]).toBe(direct);

    hook.tabs.push({ id: 321, content: "new" } as FakeTab);
    hook.render(renderedTabs, true);

    expect(renderedTabs.map((tab) => tab.key)).toEqual([
      "native",
      999,
      PDC_QAM_TAB_ID,
      321,
    ]);
    expect(renderedTabs[1]).toBe(standard);
    expect(renderedTabs[2]).toBe(direct);
    expect(renderedTabs[3]).not.toBe(thirdPartyRendered);
  });

  it("requires a restart when the renderer probe mutates the real registry", () => {
    const hook = createHook();
    hook.render = () => {
      hook.tabs = [];
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("unsafe_renderer");
    expect(result.restartRequired).toBe(true);
    expect(hook.tabs).toHaveLength(0);
  });

  it("requires a restart when the renderer probe mutates the registry and throws", () => {
    const hook = createHook();
    hook.render = () => {
      hook.tabs = [];
      throw new Error("Decky renderer failed");
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("unsafe_renderer");
    expect(result.restartRequired).toBe(true);
    expect(hook.tabs).toHaveLength(0);
  });

  it("requires a restart when the renderer probe mutates the standard tab id", () => {
    const hook = createHook();
    hook.render = function (this: { tabs: FakeTab[] }, existingTabs: RenderedTab[]) {
      hook.tabs[0].id = 123;
      existingTabs.splice(
        0,
        existingTabs.length,
        { key: "native" },
        ...this.tabs.map((tab) => ({ decky: true, key: tab.id })),
      );
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("unsafe_renderer");
    expect(result.restartRequired).toBe(true);
    expect(hook.tabs.some((tab) => tab.id === 999)).toBe(false);
  });

  it("requires a restart when the renderer probe mutates standard tab content", () => {
    const hook = createHook();
    hook.render = function (this: { tabs: FakeTab[] }, existingTabs: RenderedTab[]) {
      hook.tabs[0].content = null;
      const nativeTabs = existingTabs.filter((tab) => !tab.decky);
      existingTabs.splice(
        0,
        existingTabs.length,
        ...nativeTabs,
        ...this.tabs.map((tab) => ({ decky: true, key: tab.id })),
      );
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("unsafe_renderer");
    expect(result.restartRequired).toBe(true);
  });

  it("requires a restart when the registry readback throws after the renderer probe", () => {
    const hook = createHook();
    hook.render = function (this: { tabs: FakeTab[] }, existingTabs: RenderedTab[]) {
      const nativeTabs = existingTabs.filter((tab) => !tab.decky);
      existingTabs.splice(
        0,
        existingTabs.length,
        ...nativeTabs,
        ...this.tabs.map((tab) => ({ decky: true, key: tab.id })),
      );
      Object.defineProperty(hook, "tabs", {
        configurable: true,
        get() {
          throw new Error("Decky registry unavailable");
        },
      });
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("unsafe_renderer");
    expect(result.restartRequired).toBe(true);
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

  it("releases the adapter when another actor already removed the owned tab", () => {
    const hook = createHook();
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const originalRender = hook.render;
    const renderedTabs = [{ key: "native" }, { decky: true, key: 999, panel: {} }];
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );
    hook.render(renderedTabs, true);
    hook.tabs = hook.tabs.filter((tab) => tab.id !== PDC_QAM_TAB_ID);
    hook.render(renderedTabs, true);

    result.dispose();

    expect(renderedTabs.map((tab) => tab.key)).toEqual(["native", 999]);
    expect(hook.render).toBe(originalRender);
  });

  it("requires a restart without overwriting a foreign renderer", () => {
    const hook = createHook();
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const host = { __TABS_HOOK_INSTANCE: hook };
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    const foreignRenderer = vi.fn();
    hook.render = foreignRenderer;

    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
    expect(hook.render).toBe(foreignRenderer);
    expect(hook.tabs.some((tab) => tab.id === PDC_QAM_TAB_ID)).toBe(true);
  });

  it("retains the restart signal when disposal removes the standard Decky tab", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    hook.removeById = () => {
      hook.tabs = [];
    };

    result.dispose();

    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
  });

  it("retains the restart signal when disposal removes ownership from its tab", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    hook.removeById = () => {
      const tab = hook.tabs.find((candidate) => candidate.id === PDC_QAM_TAB_ID);
      if (tab) delete tab.__pdcOwner;
    };

    result.dispose();

    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
  });

  it("retains the restart signal when disposal mutates standard tab content", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    hook.removeById = (id: number) => {
      hook.tabs = hook.tabs.filter((tab) => tab.id !== id);
      hook.tabs[0].content = null;
    };

    result.dispose();

    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
  });

  it("retains the restart signal when disposal throws", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    hook.removeById = () => {
      throw new Error("Decky cleanup failed");
    };

    result.dispose();
    hook.removeById = (id: number) => {
      hook.tabs = hook.tabs.filter((tab) => tab.id !== id);
    };

    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
  });

  it("reports that a restart is required when cleanup cannot remove an owned tab", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    hook.render = appendRegistryOnCountChange;

    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(1);
  });

  it("requires a restart when cleanup also removes the standard Decky tab", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    hook.removeById = () => {
      hook.tabs = [];
    };

    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
    expect(hook.tabs).toHaveLength(0);
  });

  it("requires a restart when cleanup mutates the standard Decky tab id", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    hook.removeById = (id: number) => {
      hook.tabs = hook.tabs.filter((tab) => tab.id !== id);
      hook.tabs[0].id = 123;
    };

    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
    expect(hook.tabs.some((tab) => tab.id === 999)).toBe(false);
  });

  it("requires a restart when cleanup mutates standard tab content", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    hook.removeById = (id: number) => {
      hook.tabs = hook.tabs.filter((tab) => tab.id !== id);
      hook.tabs[0].content = null;
    };

    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
  });

  it("retains cleanup corruption across subsequent reconciliation", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );
    hook.removeById = (id: number) => {
      hook.tabs = hook.tabs.filter((tab) => tab.id !== id);
      hook.tabs[0].content = null;
      throw new Error("Decky cleanup failed");
    };

    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
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

  it("requires a restart when replacing a stale tab removes the standard Decky tab", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    registerQuickAccessTab(
      { title: "Old", content: "old panel", icon: "old icon" },
      host,
    );
    hook.removeById = () => {
      hook.tabs = [];
    };

    const result = registerQuickAccessTab(
      { title: "Current", content: "current panel", icon: "current icon" },
      host,
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("cleanup_failed");
    expect(result.restartRequired).toBe(true);
    expect(hook.tabs).toHaveLength(0);
  });

  it("cleans an owned tab left behind by an earlier loader session", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    registerQuickAccessTab(
      { title: "Old", content: "old panel", icon: "old icon" },
      host,
    );

    const restartRequired = cleanupOwnedQuickAccessTabs(host);

    expect(restartRequired).toBe(false);
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

  it("requires a restart when a failed add leaves a partial registration", () => {
    const hook = createHook();
    hook.add = (tab: FakeTab) => {
      hook.tabs.push(tab);
      hook.render = appendRegistryOnCountChange;
      throw new Error("Decky render failed");
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.restartRequired).toBe(true);
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(1);
  });

  it("requires a restart when failed-add cleanup restores tabs but cannot release the adapter", () => {
    const hook = createHook();
    useInheritedRenderer(hook, appendRegistryOnCountChange);
    const foreignRenderer = vi.fn();
    hook.add = (tab: FakeTab) => {
      hook.tabs.push(tab);
      throw new Error("Decky add failed");
    };
    hook.removeById = (id: number) => {
      hook.tabs = hook.tabs.filter((tab) => tab.id !== id);
      hook.render = foreignRenderer;
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.restartRequired).toBe(true);
    expect(hook.tabs.map((tab) => tab.id)).toEqual([999]);
    expect(hook.render).toBe(foreignRenderer);
  });

  it("requires a restart when cleanup throws after a partial add", () => {
    const hook = createHook();
    hook.add = (tab: FakeTab) => {
      hook.tabs.push(tab);
      throw new Error("Decky add failed");
    };
    hook.removeById = () => {
      throw new Error("Decky cleanup failed");
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("add_failed");
    expect(result.restartRequired).toBe(true);
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(1);
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

  it("requires a restart when add replaces the standard Decky tab", () => {
    const hook = createHook();
    hook.add = (tab: FakeTab) => {
      hook.tabs = [tab];
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("registry_mismatch");
    expect(result.restartRequired).toBe(true);
    expect(hook.tabs.some((tab) => tab.id === 999)).toBe(false);
  });

  it("requires a restart when add mutates the standard Decky tab id", () => {
    const hook = createHook();
    hook.add = (tab: FakeTab) => {
      hook.tabs[0].id = 123;
      hook.tabs.push(tab);
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("registry_mismatch");
    expect(result.restartRequired).toBe(true);
    expect(hook.tabs.some((tab) => tab.id === 999)).toBe(false);
  });

  it("requires a restart when add mutates standard tab content", () => {
    const hook = createHook();
    hook.add = (tab: FakeTab) => {
      hook.tabs[0].content = null;
      hook.tabs.push(tab);
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("registry_mismatch");
    expect(result.restartRequired).toBe(true);
  });

  it("requires a restart when add removes ownership from the new tab", () => {
    const hook = createHook();
    hook.add = (tab: FakeTab) => {
      delete tab.__pdcOwner;
      hook.tabs.push(tab);
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("registry_mismatch");
    expect(result.restartRequired).toBe(true);
  });

  it("retains add corruption across subsequent reconciliation", () => {
    const hook = createHook();
    const host = { __TABS_HOOK_INSTANCE: hook };
    hook.add = (tab: FakeTab) => {
      hook.tabs[0].content = null;
      hook.tabs.push(tab);
      throw new Error("Decky add failed");
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      host,
    );

    expect(result.restartRequired).toBe(true);
    expect(cleanupOwnedQuickAccessTabs(host)).toBe(true);
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

  it("requires a restart when cleanup throws after a registry mismatch", () => {
    const hook = createHook();
    hook.add = (tab: FakeTab) => {
      hook.tabs.push(tab, tab);
    };
    hook.removeById = () => {
      throw new Error("Decky cleanup failed");
    };

    const result = registerQuickAccessTab(
      { title: "Panel de Control", content: "panel", icon: "icon" },
      { __TABS_HOOK_INSTANCE: hook },
    );

    expect(result.registered).toBe(false);
    expect(result.reason).toBe("registry_mismatch");
    expect(result.restartRequired).toBe(true);
    expect(hook.tabs.filter((tab) => tab.id === PDC_QAM_TAB_ID)).toHaveLength(2);
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
    registerQuickAccessTab({ title: null, content: null, icon: null }, {});
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
      render_adapter_active: false,
      render_adapter_failure: null,
      render_adapter_observed_arrays: 0,
      registration_reason: "hook_unavailable",
    });
  });

  it("reports bounded QAM counts without exposing tab identifiers", () => {
    const host = {
      __TABS_HOOK_INSTANCE: {
        tabs: [{ id: 999 }, { id: PDC_QAM_TAB_ID }, { id: PDC_QAM_TAB_ID }],
      },
    };
    registerQuickAccessTab({ title: null, content: null, icon: null }, host);
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
      render_adapter_active: false,
      render_adapter_failure: null,
      render_adapter_observed_arrays: 0,
      registration_reason: "hook_unavailable",
    });
  });
});

describe("pluginInventory", () => {
  it("preserves versions and merges Decky's disabled state", () => {
    const inventory = pluginInventory({
      DeckyPluginLoader: {
        deckyState: {
          publicState: () => ({
            installedPlugins: [
              { name: "CSS Loader", version: "2.1.2" },
              { name: "Other Plugin", version: "1.0.0" },
            ],
            disabledPlugins: [{ name: "CSS Loader" }],
          }),
        },
      },
    });

    expect(inventory).toEqual([
      { name: "CSS Loader", version: "2.1.2", disabled: true },
      { name: "Other Plugin", version: "1.0.0", disabled: false },
    ]);
  });

  it("keeps a plugin that Decky exposes only in the disabled collection", () => {
    const inventory = strictPluginInventory({
      DeckyPluginLoader: {
        deckyState: {
          publicState: () => ({
            installedPlugins: [{ name: "Other Plugin", version: "1.0.0" }],
            disabledPlugins: [{ name: "CSS Loader", version: "2.1.2" }],
          }),
        },
      },
    });

    expect(inventory).toEqual([
      { name: "Other Plugin", version: "1.0.0", disabled: false },
      { name: "CSS Loader", version: "2.1.2", disabled: true },
    ]);
  });

  it("lets strict consumers distinguish an unavailable private contract from an empty inventory", () => {
    expect(() => strictPluginInventory({})).toThrow("Decky plugin inventory unavailable");
  });

  it("fails closed when one of Decky's inventory entries is malformed", () => {
    expect(() => strictPluginInventory({
      DeckyPluginLoader: {
        deckyState: {
          publicState: () => ({
            installedPlugins: [{ version: "2.1.2" }],
            disabledPlugins: [],
          }),
        },
      },
    })).toThrow("Decky installedPlugins entry 0 is invalid");
  });

  it("fails closed when Decky's state shape is unavailable", () => {
    expect(pluginInventory({})).toEqual([]);
    expect(pluginInventory({ DeckyPluginLoader: { deckyState: { publicState: () => { throw new Error("moved"); } } } })).toEqual([]);
  });
});

describe("callPluginBackend", () => {
  it("uses Decky's targeted plugin route without reconnecting as that plugin", async () => {
    const call = vi.fn(async () => ({ success: true }));

    const result = await callPluginBackend(
      "CSS Loader",
      "set_theme_state",
      ["Example Theme", true, false, false],
      { DeckyBackend: { call } },
    );

    expect(result).toEqual({ success: true });
    expect(call).toHaveBeenCalledWith(
      "loader/call_plugin_method",
      "CSS Loader",
      "set_theme_state",
      "Example Theme",
      true,
      false,
      false,
    );
  });

  it("rejects when the private Decky route is unavailable", async () => {
    await expect(callPluginBackend("CSS Loader", "get_themes", [], {}))
      .rejects.toThrow("DeckyBackend unavailable");
  });
});

describe("callLegacyPluginBackend", () => {
  it("uses Decky's current legacy target route and unwraps the plugin result", async () => {
    const call = vi.fn(async () => ({ success: true, result: ["theme"] }));

    await expect(callLegacyPluginBackend(
      "CSS Loader",
      "get_themes",
      {},
      { DeckyBackend: { call } },
    )).resolves.toEqual(["theme"]);
    expect(call).toHaveBeenCalledWith(
      "loader/call_legacy_plugin_method",
      "CSS Loader",
      "get_themes",
      {},
    );
  });

  it("fails closed when Decky or the legacy plugin rejects the call", async () => {
    await expect(callLegacyPluginBackend(
      "CSS Loader",
      "get_themes",
      {},
      { DeckyBackend: { call: vi.fn(async () => ({ success: false, result: "denied" })) } },
    )).rejects.toThrow("denied");
    await expect(callLegacyPluginBackend(
      "CSS Loader",
      "get_themes",
      {},
      { DeckyBackend: { call: vi.fn(async () => ({ unexpected: true })) } },
    )).rejects.toThrow("invalid legacy response");
  });
});
