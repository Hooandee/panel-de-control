// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

import type { CssLoaderSnapshot } from "../cssLoaderTypes";
import { createSteamRuntimeBridge, startThemesRuntime } from "./start";

const READY: CssLoaderSnapshot = { status: "ready", backendVersion: 9, themes: [] };

describe("createSteamRuntimeBridge", () => {
  it("mounts modules in Steam's Big Picture document instead of Decky's shared realm", () => {
    const sharedDocument = { title: "SharedJSContext" } as unknown as Document;
    const steamDocument = { title: "SP" } as unknown as Document;
    let current: Document | null = steamDocument;
    const reconcile = vi.fn();
    const dispose = vi.fn();
    const createManager = vi.fn(() => ({ reconcile, dispose }));
    const bridge = createSteamRuntimeBridge(() => current, createManager);

    bridge.reconcile(READY);

    expect(createManager).toHaveBeenCalledWith(steamDocument);
    expect(createManager).not.toHaveBeenCalledWith(sharedDocument);
    expect(reconcile).toHaveBeenCalledWith(READY);
  });

  it("disposes stale DOM ownership when Steam replaces or removes its window", () => {
    const firstDocument = { title: "SP 1" } as unknown as Document;
    const secondDocument = { title: "SP 2" } as unknown as Document;
    let current: Document | null = firstDocument;
    const managers = [
      { reconcile: vi.fn(), dispose: vi.fn() },
      { reconcile: vi.fn(), dispose: vi.fn() },
    ];
    const createManager = vi.fn(() => managers[createManager.mock.calls.length - 1]);
    const bridge = createSteamRuntimeBridge(() => current, createManager);

    bridge.reconcile(READY);
    current = secondDocument;
    bridge.reconcile(READY);
    expect(managers[0].dispose).toHaveBeenCalledOnce();
    expect(managers[1].reconcile).toHaveBeenCalledWith(READY);

    current = null;
    bridge.reconcile(READY);
    expect(managers[1].dispose).toHaveBeenCalledOnce();

    bridge.dispose();
    expect(managers[1].dispose).toHaveBeenCalledOnce();
  });

  it("refreshes extension receipts only when installed name/version inventory changes", async () => {
    const refreshDescriptors = vi.fn(async () => {});
    const bridge = createSteamRuntimeBridge(
      () => document,
      () => ({ reconcile: vi.fn(), refreshDescriptors, dispose: vi.fn() }),
    );
    const first = {
      status: "ready" as const,
      pluginVersion: "2.1.2",
      backendVersion: 9,
      themes: [{
        id: "Example Theme", name: "Example Theme", displayName: "Example Theme",
        version: "1.2.3", author: "Example Author", enabled: true, patches: [],
      }],
    };

    bridge.reconcile(first);
    bridge.reconcile({ ...first, themes: [{ ...first.themes[0], enabled: false }] });
    expect(refreshDescriptors).not.toHaveBeenCalled();

    bridge.reconcile({ ...first, themes: [{ ...first.themes[0], version: "1.2.4" }] });
    expect(refreshDescriptors).toHaveBeenCalledOnce();
  });

  it("fails closed when resolving Steam's document throws", () => {
    const createManager = vi.fn();
    const bridge = createSteamRuntimeBridge(() => { throw new Error("SP unavailable"); }, createManager);

    expect(() => bridge.reconcile(READY)).not.toThrow();
    expect(createManager).not.toHaveBeenCalled();
  });
});

describe("startThemesRuntime", () => {
  it("refreshes from CSS Loader stylesheet changes only while mounted", async () => {
    document.head.innerHTML = '<style class="css-loader-style">/* active theme */</style>';
    const refresh = vi.fn(async () => {});
    const unsubscribe = vi.fn();
    const client = {
      getSnapshot: () => ({ snapshot: READY }),
      subscribe: vi.fn(() => unsubscribe),
      refresh,
    };
    const stop = startThemesRuntime({
      client,
      getSteamDocument: () => document,
      createManager: () => ({ reconcile: vi.fn(), dispose: vi.fn() }),
    });

    document.querySelector("style.css-loader-style")?.remove();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(refresh).toHaveBeenCalledOnce();

    stop();
    document.head.insertAdjacentHTML(
      "beforeend",
      '<style class="css-loader-style">/* restored theme */</style>',
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("reconciles from the shared client and releases its polling lease", () => {
    const steamDocument = { title: "SP" } as unknown as Document;
    const reconcile = vi.fn();
    const dispose = vi.fn();
    const unsubscribe = vi.fn();
    let publish!: () => void;
    let current: CssLoaderSnapshot = READY;
    const client = {
      getSnapshot: () => ({ snapshot: current }),
      subscribe: vi.fn((listener: () => void, intervalMs?: number) => {
        publish = listener;
        expect(intervalMs).toBe(30_000);
        return unsubscribe;
      }),
      refresh: vi.fn(async () => {}),
    };

    const stop = startThemesRuntime({
      client,
      getSteamDocument: () => steamDocument,
      createManager: () => ({ reconcile, dispose }),
    });

    expect(reconcile).toHaveBeenCalledWith(READY);
    current = { status: "missing", themes: [] };
    publish();
    expect(reconcile).toHaveBeenLastCalledWith(current);

    stop();
    expect(unsubscribe).toHaveBeenCalledOnce();
    expect(dispose).toHaveBeenCalledOnce();
  });
});
