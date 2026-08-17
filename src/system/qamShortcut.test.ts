// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

const getUiPrefs = vi.hoisted(() => vi.fn());

vi.mock("../api", () => ({
  getUiPrefs,
  setUiPrefs: vi.fn(async () => true),
}));

describe("QAM shortcut preference", () => {
  beforeEach(() => {
    localStorage.clear();
    getUiPrefs.mockReset();
    getUiPrefs.mockResolvedValue({});
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

  it("registers synchronously and removes the tab when the durable preference is disabled", async () => {
    let resolvePrefs!: (prefs: Record<string, string>) => void;
    getUiPrefs.mockImplementation(() => new Promise((resolve) => {
      resolvePrefs = resolve;
    }));
    const state = await import("./qamShortcut");
    const dispose = vi.fn();
    const register = vi.fn(() => ({ registered: true, dispose }));
    const removeOwned = vi.fn();
    const session = state.startQamShortcut(register, removeOwned);

    expect(removeOwned).toHaveBeenCalledOnce();
    expect(register).toHaveBeenCalledOnce();
    expect(state.getQamShortcutSnapshot()).toMatchObject({
      appliedEnabled: true,
      registered: true,
      initialized: true,
    });
    resolvePrefs({ "pdc:qamShortcut": "0" });
    await session.ready;
    expect(register).toHaveBeenCalledOnce();
    expect(dispose).toHaveBeenCalledOnce();
    expect(removeOwned).toHaveBeenCalledTimes(2);
    expect(state.getQamShortcutSnapshot()).toMatchObject({
      enabled: false,
      appliedEnabled: false,
      registered: false,
      initialized: true,
    });
  });

  it("requires a restart instead of registering late when hydration enables the shortcut", async () => {
    localStorage.setItem("pdc:qamShortcut", "0");
    getUiPrefs.mockResolvedValue({ "pdc:qamShortcut": "1" });
    const state = await import("./qamShortcut");
    const register = vi.fn(() => ({ registered: true, dispose: vi.fn() }));

    const removeOwned = vi.fn();
    const session = state.startQamShortcut(register, removeOwned);
    expect(removeOwned).toHaveBeenCalledOnce();
    await session.ready;

    expect(register).not.toHaveBeenCalled();
    expect(state.getQamShortcutSnapshot()).toMatchObject({
      enabled: true,
      appliedEnabled: false,
      registered: false,
      initialized: true,
      restartRequired: true,
    });
  });

  it("keeps the standard entry initialized when preference hydration fails", async () => {
    localStorage.setItem("pdc:qamShortcut", "0");
    getUiPrefs.mockRejectedValue(new Error("backend unavailable"));
    const state = await import("./qamShortcut");

    const session = state.startQamShortcut(vi.fn(), vi.fn());

    expect(state.getQamShortcutSnapshot()).toMatchObject({
      appliedEnabled: false,
      registered: false,
      initialized: true,
    });
    await session.ready;
  });

  it("requires a restart when disabling cannot clear an obsolete direct tab", async () => {
    localStorage.setItem("pdc:qamShortcut", "0");
    const state = await import("./qamShortcut");

    const session = state.startQamShortcut(vi.fn(), () => true);

    expect(state.getQamShortcutSnapshot()).toMatchObject({
      enabled: false,
      appliedEnabled: false,
      registered: false,
      restartRequired: true,
    });
    await session.ready;
  });

  it("publishes a restart immediately when the registered shortcut fails at runtime", async () => {
    const state = await import("./qamShortcut");
    let failRuntime!: () => void;
    state.startQamShortcut(
      (onRuntimeFailure) => {
        failRuntime = onRuntimeFailure;
        return { registered: true, dispose() {} };
      },
      () => false,
    );

    failRuntime();

    expect(state.getQamShortcutSnapshot()).toMatchObject({
      registered: false,
      restartRequired: true,
    });
  });

  it("does not erase a runtime failure when preference hydration completes", async () => {
    let resolvePrefs!: (prefs: Record<string, string>) => void;
    getUiPrefs.mockImplementation(() => new Promise((resolve) => {
      resolvePrefs = resolve;
    }));
    const state = await import("./qamShortcut");
    let failRuntime!: () => void;
    const session = state.startQamShortcut(
      (onRuntimeFailure) => {
        failRuntime = onRuntimeFailure;
        return { registered: true, dispose() {} };
      },
      () => false,
    );

    failRuntime();
    resolvePrefs({ "pdc:qamShortcut": "1" });
    await session.ready;

    expect(state.getQamShortcutSnapshot()).toMatchObject({
      registered: false,
      restartRequired: true,
    });
  });
});
