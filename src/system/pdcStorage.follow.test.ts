// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

const backend: { prefs: Record<string, string> } = { prefs: {} };
const setUiPrefs = vi.fn(async () => true);

vi.mock("../api", () => ({
  getUiPrefs: vi.fn(async () => ({ ...backend.prefs })),
  setUiPrefs,
}));

async function load() {
  vi.resetModules();
  return import("./pdcStorage");
}

beforeEach(() => {
  window.localStorage.clear();
  backend.prefs = {};
  setUiPrefs.mockClear();
});

describe("followBackendPrefs", () => {
  it("mirrors the backend and never pushes stale local keys up", async () => {
    const storage = await load();
    window.localStorage.setItem("pdc:views", "old");
    window.localStorage.setItem("pdc:deletedInQam", "1");
    backend.prefs = { "pdc:views": "new" };

    storage.becomePrefsFollower();
    await storage.hydratePrefs();

    expect(window.localStorage.getItem("pdc:views")).toBe("new");
    expect(window.localStorage.getItem("pdc:deletedInQam")).toBeNull();
    expect(setUiPrefs).not.toHaveBeenCalled();
    expect(storage.prefsHydrated()).toBe(true);
  });

  it("keeps a fresh local write until the backend has had time to catch up", async () => {
    const storage = await load();
    let now = 1_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
    storage.writeString("pdc:accent", "teal");
    backend.prefs = { "pdc:accent": "blue" };

    await storage.followBackendPrefs(() => now);
    expect(window.localStorage.getItem("pdc:accent")).toBe("teal");

    now += 11_000;
    await storage.followBackendPrefs(() => now);
    expect(window.localStorage.getItem("pdc:accent")).toBe("blue");
    vi.restoreAllMocks();
  });

  it("tells listeners only when something changed", async () => {
    const storage = await load();
    const healed = vi.fn();
    storage.onPrefsHealed(healed);
    backend.prefs = { "pdc:views": "a" };
    await storage.followBackendPrefs();
    await storage.followBackendPrefs();
    expect(healed).toHaveBeenCalledTimes(1);
  });
});
