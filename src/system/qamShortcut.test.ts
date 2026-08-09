// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  getUiPrefs: vi.fn(async () => ({})),
  setUiPrefs: vi.fn(async () => true),
}));

describe("QAM shortcut preference", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  it("defaults to enabled when no preference exists", async () => {
    const state = await import("./qamShortcut");

    expect(state.getQamShortcutEnabled()).toBe(true);
    expect(state.getQamShortcutSnapshot().enabled).toBe(true);
  });

  it("persists disabled and reports a restart while the active session remains enabled", async () => {
    const state = await import("./qamShortcut");
    state.setQamShortcutRuntime(true, true);

    state.setQamShortcutEnabled(false);

    expect(localStorage.getItem("pdc:qamShortcut")).toBe("0");
    expect(state.getQamShortcutSnapshot()).toMatchObject({
      enabled: false,
      appliedEnabled: true,
      registered: true,
      restartRequired: true,
    });
  });

  it("notifies subscribers when hydration changes the cached preference", async () => {
    const state = await import("./qamShortcut");
    const snapshots: boolean[] = [];
    const unsubscribe = state.subscribeQamShortcut(() => {
      snapshots.push(state.getQamShortcutSnapshot().enabled);
    });

    localStorage.setItem("pdc:qamShortcut", "0");
    state.refreshQamShortcutPreference();

    expect(snapshots).toEqual([false]);
    unsubscribe();
  });

  it("keeps the external-store snapshot stable between changes", async () => {
    const state = await import("./qamShortcut");

    expect(state.getQamShortcutSnapshot()).toBe(state.getQamShortcutSnapshot());
  });
});
