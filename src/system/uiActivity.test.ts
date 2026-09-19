import { describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ setUiActive: vi.fn(async () => true) }));

import {
  createSteamOverlayActivityBridge,
  createUiActivityCoordinator,
  startSteamOverlayActivity,
} from "./uiActivity";

const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe("UI activity coordinator", () => {
  it("keeps the backend active while any visible panel owner remains", async () => {
    const writes: boolean[] = [];
    const activity = createUiActivityCoordinator(async (active) => {
      writes.push(active);
    });
    const releaseA = activity.acquire();
    const releaseB = activity.acquire();
    await settle();

    releaseA();
    await settle();
    expect(writes).toEqual([true]);

    releaseB();
    await settle();
    expect(writes).toEqual([true, false]);
  });

  it("coalesces a same-turn handoff between QAM panels", async () => {
    const writes: boolean[] = [];
    const activity = createUiActivityCoordinator(async (active) => {
      writes.push(active);
    });
    const release = activity.acquire();
    await settle();

    release();
    activity.acquire();
    await settle();

    expect(writes).toEqual([true]);
  });

  it("makes each release idempotent", async () => {
    const writes: boolean[] = [];
    const activity = createUiActivityCoordinator(async (active) => {
      writes.push(active);
    });
    const release = activity.acquire();
    await settle();

    release();
    release();
    await settle();

    expect(writes).toEqual([true, false]);
  });

  it("retries a transient backend failure while the panel stays open", async () => {
    vi.useFakeTimers();
    try {
      const write = vi.fn()
        .mockRejectedValueOnce(new Error("backend unavailable"))
        .mockResolvedValue(undefined);
      const activity = createUiActivityCoordinator(write);

      activity.acquire();
      await vi.advanceTimersByTimeAsync(250);

      expect(write).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("forces deactivation when activation may have mutated before failing", async () => {
    let backendActive = false;
    const writes: boolean[] = [];
    const activity = createUiActivityCoordinator(async (active) => {
      writes.push(active);
      backendActive = active;
      if (active) throw new Error("response lost after mutation");
    });

    const release = activity.acquire();
    await settle();
    release();
    await settle();

    expect(writes).toEqual([true, false]);
    expect(backendActive).toBe(false);
  });

  it("bounds retries when the backend remains unavailable", async () => {
    vi.useFakeTimers();
    try {
      const write = vi.fn(async () => {
        throw new Error("backend unavailable");
      });
      const activity = createUiActivityCoordinator(write);

      activity.acquire();
      await vi.advanceTimersByTimeAsync(5000);

      expect(write).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it("serializes a shutdown after an in-flight activation", async () => {
    let finishActivation!: () => void;
    const activation = new Promise<void>((resolve) => {
      finishActivation = resolve;
    });
    const writes: boolean[] = [];
    const write = vi.fn(async (active: boolean) => {
      writes.push(active);
      if (active) await activation;
    });
    const activity = createUiActivityCoordinator(write);

    activity.acquire();
    await Promise.resolve();
    activity.shutdown();
    finishActivation();
    await settle();

    expect(writes).toEqual([true, false]);
  });
});

describe("Steam overlay activity", () => {
  it("registers through Steam's injected global service", () => {
    const unregister = vi.fn();
    const register = vi.fn(() => ({ unregister }));
    const previous = Object.getOwnPropertyDescriptor(globalThis, "SteamClient");
    Object.defineProperty(globalThis, "SteamClient", {
      configurable: true,
      value: { Overlay: { RegisterForOverlayActivated: register } },
    });

    try {
      const stop = startSteamOverlayActivity();
      expect(register).toHaveBeenCalledOnce();
      stop();
      expect(unregister).toHaveBeenCalledOnce();
    } finally {
      if (previous) Object.defineProperty(globalThis, "SteamClient", previous);
      else Reflect.deleteProperty(globalThis, "SteamClient");
    }
  });

  it("holds one activity owner while the game overlay is visible", () => {
    let onOverlay!: (_pid: number, _appid: number, active: boolean) => void;
    const unregister = vi.fn();
    const release = vi.fn();
    const acquire = vi.fn(() => release);
    const stop = createSteamOverlayActivityBridge(acquire, {
      RegisterForOverlayActivated(callback) {
        onOverlay = callback;
        return { unregister };
      },
    });

    onOverlay(10, 814380, true);
    onOverlay(10, 814380, true);
    expect(acquire).toHaveBeenCalledOnce();

    onOverlay(10, 814380, false);
    expect(release).toHaveBeenCalledOnce();

    stop();
    expect(unregister).toHaveBeenCalledOnce();
    expect(release).toHaveBeenCalledOnce();
  });

  it("is a safe no-op when Steam does not expose overlay activity", () => {
    const acquire = vi.fn(() => vi.fn());
    const stop = createSteamOverlayActivityBridge(acquire, undefined);

    stop();

    expect(acquire).not.toHaveBeenCalled();
  });
});
