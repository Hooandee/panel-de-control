import { describe, expect, it, vi } from "vitest";

import type { CssLoaderSnapshot } from "../cssLoaderTypes";
import { createSteamRuntimeBridge } from "./start";

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

  it("fails closed when resolving Steam's document throws", () => {
    const createManager = vi.fn();
    const bridge = createSteamRuntimeBridge(() => { throw new Error("SP unavailable"); }, createManager);

    expect(() => bridge.reconcile(READY)).not.toThrow();
    expect(createManager).not.toHaveBeenCalled();
  });
});
