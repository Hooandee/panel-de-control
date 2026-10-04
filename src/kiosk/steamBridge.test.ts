import { describe, expect, it, vi } from "vitest";

vi.mock("@decky/api", () => ({ addEventListener: vi.fn(), removeEventListener: vi.fn() }));
vi.mock("@decky/ui", () => ({ Navigation: { OpenQuickAccessMenu: vi.fn() } }));
vi.mock("../api", () => ({ kioskSteamResult: vi.fn(async () => true) }));
vi.mock("../deckyInternal", () => ({ callBackend: vi.fn() }));
vi.mock("../system/display", () => ({ displayBrightness: { subscribe: () => null, set: () => {} } }));
vi.mock("../steam/performanceRuntime", () => ({ resolveSteamPerformanceStore: () => null }));
vi.mock("../system/audio", () => ({ systemVolume: { subscribe: () => null, set: () => {} } }));
vi.mock("./deckPerf", () => ({ steamDeckPerf: () => ({}) }));
vi.mock("../system/colores", () => ({
  COLORES_PLUGIN_NAME: "Colores",
  installColores: vi.fn(),
  isColoresInstalled: vi.fn(),
  waitForColoresInstalled: vi.fn(),
}));

import { BridgeDeps, createBridgeHandlers } from "./steamBridge";

function deps(patch: Partial<BridgeDeps> = {}): BridgeDeps & { sets: Record<string, number[]> } {
  const sets: Record<string, number[]> = { brightness: [], volume: [] };
  const scalar = (name: string, current: number) => ({
    subscribe: (cb: (v: number) => void) => {
      cb(current);
      return () => {};
    },
    set: (v: number) => sets[name].push(v),
  });
  return {
    sets,
    perf: {},
    brightness: scalar("brightness", 0.62),
    volume: scalar("volume", 0.45),
    perfStore: () => ({
      msgLimits: { is_manual_display_refresh_rate_available: true, display_refresh_manual_hz_min: 60, display_refresh_manual_hz_max: 120 },
      msgSettingsPerApp: { display_refresh_manual_hz: 120 },
      SetDisplayRefreshRateManualHz: vi.fn(),
    }),
    showKeyboard: () => true,
    takeScreenshot: () => true,
    openQuickAccess: vi.fn(),
    colores: { installed: () => true, call: vi.fn(async () => ({ ok: 1 })), install: vi.fn(async () => true) },
    ...patch,
  };
}

describe("kiosk Steam bridge handlers", () => {
  it("reads the last brightness and volume Steam pushed and writes clamped fractions", () => {
    const d = deps();
    const { handlers } = createBridgeHandlers(d);
    expect(handlers["brightness.get"]([])).toEqual({ value: 0.62 });
    expect(handlers["volume.get"]([])).toEqual({ value: 0.45 });
    handlers["brightness.set"]([1.4]);
    handlers["volume.set"]([0.3]);
    expect(d.sets).toEqual({ brightness: [1], volume: [0.3] });
    expect(() => handlers["volume.set"](["loud"])).toThrow("bad_value");
  });

  it("reports the real refresh range and refuses rates outside it", () => {
    const store = {
      msgLimits: { is_manual_display_refresh_rate_available: true, display_refresh_manual_hz_min: 60, display_refresh_manual_hz_max: 120 },
      msgSettingsPerApp: { display_refresh_manual_hz: 120 },
      SetDisplayRefreshRateManualHz: vi.fn(),
    };
    const { handlers } = createBridgeHandlers(deps({ perfStore: () => store }));
    expect(handlers["refresh.get"]([])).toEqual({ current: 120, min: 60, max: 120, settable: true });
    handlers["refresh.set"]([60]);
    expect(store.SetDisplayRefreshRateManualHz).toHaveBeenCalledWith(60);
    expect(() => handlers["refresh.set"]([144])).toThrow("bad_value");
  });

  it("shows the rate but refuses to switch when Steam does not manage it", () => {
    const store = {
      msgLimits: {
        is_manual_display_refresh_rate_available: true,
        display_refresh_manual_hz_min: 60,
        display_refresh_manual_hz_max: 120,
        disable_refresh_rate_management: true,
      },
      msgSettingsPerApp: { display_refresh_manual_hz: 120 },
      SetDisplayRefreshRateManualHz: vi.fn(),
    };
    const { handlers } = createBridgeHandlers(deps({ perfStore: () => store }));
    expect(handlers["refresh.get"]([])).toEqual({ current: 120, min: 60, max: 120, settable: false });
    expect(() => handlers["refresh.set"]([60])).toThrow("unsupported");
    expect(store.SetDisplayRefreshRateManualHz).not.toHaveBeenCalled();
  });

  it("says when a Steam feature is missing instead of pretending", () => {
    const { handlers } = createBridgeHandlers(deps({ perfStore: () => null, showKeyboard: () => false, takeScreenshot: () => false }));
    expect(handlers["refresh.get"]([])).toBeNull();
    expect(() => handlers.keyboard([])).toThrow("unsupported");
    expect(() => handlers.screenshot([])).toThrow("unsupported");
  });

  it("only forwards allowed Colores methods, and only when Colores is installed", async () => {
    const d = deps();
    const { handlers } = createBridgeHandlers(d);
    await handlers["colores.call"](["set_effect", ["rainbow", 50, false]]);
    expect(d.colores.call).toHaveBeenCalledWith("set_effect", ["rainbow", 50, false]);
    await expect(handlers["colores.call"](["submit_report", []])).rejects.toThrow("unknown_method");
    const missing = createBridgeHandlers(deps({ colores: { ...d.colores, installed: () => false } }));
    expect(await missing.handlers["colores.state"]([])).toEqual({ installed: false });
    await expect(missing.handlers["colores.call"](["set_power", [true]])).rejects.toThrow("not_installed");
  });

  it("answers a snapshot of every polled value in one round trip, each settled on its own", async () => {
    const perf = { "perf.view": vi.fn(async () => ({ ready: true })) };
    const { handlers } = createBridgeHandlers(deps({ perf, perfStore: () => null }));
    const snapshot = (await handlers.snapshot([])) as Record<string, { ok: boolean; result?: unknown }>;
    expect(snapshot["brightness.get"]).toEqual({ ok: true, result: { value: 0.62 } });
    expect(snapshot["volume.get"]).toEqual({ ok: true, result: { value: 0.45 } });
    expect(snapshot["refresh.get"]).toEqual({ ok: true, result: null });
    expect(snapshot["perf.view"]).toEqual({ ok: true, result: { ready: true } });
    expect(snapshot["colores.state"].ok).toBe(true);
  });
});
