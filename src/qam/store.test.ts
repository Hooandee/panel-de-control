import { beforeEach, describe, expect, it, vi } from "vitest";

const storage = vi.hoisted(() => new Map<string, string>());
const healed = vi.hoisted(() => new Set<() => void>());
const hydration = vi.hoisted(() => ({ complete: true }));

vi.mock("../system/pdcStorage", () => ({
  readString: (key: string) => storage.get(key) ?? null,
  readFlag: (key: string, fallback = false) => {
    const value = storage.get(key);
    return value === undefined ? fallback : value === "1";
  },
  writeString: (key: string, value: string) => { storage.set(key, value); },
  removeString: (key: string) => { storage.delete(key); },
  onPrefsHealed: (listener: () => void) => {
    healed.add(listener);
    return () => healed.delete(listener);
  },
  prefsHydrated: () => hydration.complete,
}));

describe("QAM layout store", () => {
  beforeEach(() => {
    storage.clear();
    healed.clear();
    hydration.complete = true;
    vi.resetModules();
  });

  it("does not persist a default before durable preferences hydrate", async () => {
    hydration.complete = false;
    const store = await import("./store");

    expect(store.getQamLayout().pinnedViews).toEqual(["pdc:home"]);
    expect(storage.has("pdc:qamLayout")).toBe(false);

    hydration.complete = true;
    storage.set("pdc:qamLayout", JSON.stringify({
      order: ["pdc:section:hud"],
      hiddenNative: ["native:friends"],
      pinnedViews: ["pdc:section:hud"],
      ownedIds: { "pdc:section:hud": 5260356 },
    }));
    healed.forEach((listener) => listener());

    expect(store.getQamLayout().pinnedViews).toEqual(["pdc:section:hud"]);
    expect(store.getQamLayout().hiddenNative).toEqual(["native:friends"]);
  });

  it("migrates the enabled legacy shortcut to a pinned Inicio once", async () => {
    storage.set("pdc:qamShortcut", "1");
    const store = await import("./store");

    expect(store.getQamLayout()).toEqual({
      order: ["pdc:home"],
      hiddenNative: [],
      pinnedViews: ["pdc:home"],
      ownedIds: {},
    });
    expect(JSON.parse(storage.get("pdc:qamLayout")!)).toEqual(store.getQamLayout());
  });

  it("does not pin Inicio when the legacy shortcut was disabled", async () => {
    storage.set("pdc:qamShortcut", "0");
    const store = await import("./store");

    expect(store.getQamLayout()).toEqual({
      order: [],
      hiddenNative: [],
      pinnedViews: [],
      ownedIds: {},
    });
  });

  it("persists a new immutable snapshot and notifies subscribers", async () => {
    const store = await import("./store");
    const listener = vi.fn();
    const unsubscribe = store.subscribeQamLayout(listener);
    const next = {
      ...store.getQamLayout(),
      pinnedViews: ["pdc:section:hud"],
    };

    store.saveQamLayout(next);

    expect(store.getQamLayout()).toBe(next);
    expect(JSON.parse(storage.get("pdc:qamLayout")!)).toEqual(next);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("heals corrupt persisted data without throwing", async () => {
    storage.set("pdc:qamLayout", JSON.stringify({
      order: 5,
      hiddenNative: ["native:help", false],
      pinnedViews: "hud",
      ownedIds: null,
    }));
    const store = await import("./store");

    expect(store.getQamLayout()).toEqual({
      order: [],
      hiddenNative: ["native:help"],
      pinnedViews: [],
      ownedIds: {},
    });
  });

  it("resets to an explicit default that cannot re-run legacy migration", async () => {
    storage.set("pdc:qamShortcut", "1");
    const store = await import("./store");
    store.saveQamLayout({
      order: ["native:friends"],
      hiddenNative: [],
      pinnedViews: [],
      ownedIds: {},
    });

    store.resetQamLayout();

    expect(store.getQamLayout()).toEqual({
      order: [],
      hiddenNative: [],
      pinnedViews: [],
      ownedIds: {},
    });
    expect(JSON.parse(storage.get("pdc:qamLayout")!)).toEqual(store.getQamLayout());

    healed.forEach((listener) => listener());
    expect(store.getQamLayout().pinnedViews).toEqual([]);
  });
});
