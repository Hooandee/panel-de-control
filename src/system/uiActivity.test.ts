import { describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ setUiActive: vi.fn(async () => true) }));

import { createUiActivityCoordinator } from "./uiActivity";

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

  it("does not retry forever when the backend call rejects", async () => {
    const write = vi.fn(async () => {
      throw new Error("backend unavailable");
    });
    const activity = createUiActivityCoordinator(write);

    activity.acquire();
    await settle();

    expect(write).toHaveBeenCalledOnce();
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
