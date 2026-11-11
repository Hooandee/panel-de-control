import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { healPoisonedComputeds, startCollectionsHeal } from "./healCollections";

const STALE = 2;

function poisoned() {
  return { derivation: () => undefined, value_: { cause: new TypeError("Cannot read properties of undefined (reading 'values')") }, observing_: [], dependenciesState_: 0, onBecomeStale_: vi.fn() };
}

function storeWith(values: Record<string, unknown>, loaded = true) {
  const admin = { values_: new Map(Object.entries(values)) };
  const store: Record<string | symbol, unknown> = { [Symbol("mobx administration")]: admin };
  if (loaded) store.m_mapCollectionsFromStorage = new Map();
  return store;
}

describe("healPoisonedComputeds", () => {
  it("marks stale only computeds that cached an error and track nothing", () => {
    const broken = poisoned();
    const healthy = { derivation: () => undefined, value_: [], observing_: [], dependenciesState_: 0, onBecomeStale_: vi.fn() };
    const tracking = { ...poisoned(), observing_: [{}] };
    const observable = { value_: { cause: new Error("x") } };
    expect(healPoisonedComputeds(storeWith({ userCollections: broken, a: healthy, b: tracking, c: observable }))).toBe(1);
    expect(broken.dependenciesState_).toBe(STALE);
    expect(broken.onBecomeStale_).toHaveBeenCalledOnce();
    expect(healthy.onBecomeStale_).not.toHaveBeenCalled();
    expect(tracking.onBecomeStale_).not.toHaveBeenCalled();
  });

  it("returns 0 for a store without a MobX administration", () => {
    expect(healPoisonedComputeds({})).toBe(0);
    expect(healPoisonedComputeds(undefined)).toBe(0);
  });
});

describe("startCollectionsHeal", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("waits for Steam's collections, heals once and stops", () => {
    const broken = poisoned();
    const store = storeWith({ userCollections: broken }, false);
    const healed = vi.fn();
    const stop = startCollectionsHeal(() => store, healed);
    vi.advanceTimersByTime(9_000);
    expect(broken.onBecomeStale_).not.toHaveBeenCalled();
    store.m_mapCollectionsFromStorage = new Map();
    vi.advanceTimersByTime(3_000);
    expect(broken.onBecomeStale_).toHaveBeenCalledOnce();
    expect(healed).toHaveBeenCalledWith(1);
    vi.advanceTimersByTime(30_000);
    expect(broken.onBecomeStale_).toHaveBeenCalledOnce();
    stop();
  });

  it("gives up after its window when the collections never load", () => {
    const store = storeWith({}, false);
    const healed = vi.fn();
    startCollectionsHeal(() => store, healed);
    vi.advanceTimersByTime(11 * 60_000);
    store.m_mapCollectionsFromStorage = new Map();
    vi.advanceTimersByTime(10_000);
    expect(healed).not.toHaveBeenCalled();
  });
});
