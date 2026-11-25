// @vitest-environment happy-dom
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  navigation: { CloseSideMenus: vi.fn() }, router: { WindowStore: {} as any },
  running: vi.fn(), press: vi.fn(), hold: vi.fn(), toast: vi.fn(), event: vi.fn(),
}));
vi.mock("@decky/api", () => ({ toaster: { toast: mocks.toast } }));
vi.mock("../i18n", () => ({ translate: (key: string) => key }));
vi.mock("../system/uiEvents", () => ({ recordUiEvent: mocks.event }));
vi.mock("@decky/ui", () => ({ Navigation: mocks.navigation, Router: mocks.router }));
vi.mock("../tdp/runningGame", () => ({ readRunningGame: mocks.running }));
vi.mock("../api", () => ({ pressUpscalerKey: mocks.press }));
vi.mock("./pageMemory", () => ({ holdPage: mocks.hold }));
import { pressUpscalerKeyInGame } from "./gameHotkey";

let focused: { Value: number };
let navigate: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  focused = { Value: 769 };
  navigate = vi.fn();
  mocks.router.WindowStore = { GamepadUIMainWindowInstance: {
    NavigateToRunningApp: navigate,
    m_CompositionStateStore: { GetCurrentlyFocusedAppidSubscribableValue: () => focused },
  } };
  mocks.running.mockReturnValue({ appid: "548430", liveAppid: 548430, name: "Deep Rock Galactic" });
  mocks.press.mockResolvedValue({ pressed: "menu" });
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it.each(["menu", "fps", "fg", "fps_style"] as const)("returns from Steam Home before emitting %s", async (action) => {
  mocks.press.mockResolvedValue({ pressed: action });
  const result = pressUpscalerKeyInGame("548430", action);
  expect(navigate).toHaveBeenCalledWith(false);
  expect(navigate.mock.invocationCallOrder[0]).toBeLessThan(mocks.navigation.CloseSideMenus.mock.invocationCallOrder[0]);
  await vi.advanceTimersByTimeAsync(100);
  expect(mocks.press).not.toHaveBeenCalled();
  focused.Value = 548430;
  await vi.advanceTimersByTimeAsync(50);
  await expect(result).resolves.toEqual({ pressed: action });
  expect(mocks.press).toHaveBeenCalledExactlyOnceWith("548430", action);
});

it("ends with an error when Steam retains focus and never emits the key", async () => {
  const result = pressUpscalerKeyInGame("548430", "fg");
  const rejected = expect(result).rejects.toThrow("game_focus_timeout");
  await vi.advanceTimersByTimeAsync(2500);
  await rejected;
  expect(mocks.press).not.toHaveBeenCalled();
  expect(vi.getTimerCount()).toBe(0);
  expect(mocks.toast).toHaveBeenCalledWith({ title: "Panel de Control", body: "up.live.failed" });
  expect(mocks.event).toHaveBeenCalledWith("upscalers", "hotkey_error", { appid: 548430, action: "fg", stage: "focus", code: "game_focus_timeout" }, false);
});

it("does not send to a different game if the running session changes while waiting", async () => {
  const result = pressUpscalerKeyInGame("548430", "fps");
  const rejected = expect(result).rejects.toThrow("game_changed");
  mocks.running.mockReturnValue({ appid: "20", liveAppid: 20, name: "Other" });
  focused.Value = 20;
  await vi.advanceTimersByTimeAsync(50);
  await rejected;
  expect(mocks.press).not.toHaveBeenCalled();
});

it.each(["shortcut-name", "3000000001"])("matches non-Steam identity %s but waits for its live app id", async (appid) => {
  mocks.running.mockReturnValue({ appid: "shortcut-name", liveAppid: 3000000001, name: "Shortcut" });
  const result = pressUpscalerKeyInGame(appid, "menu");
  focused.Value = 3000000001;
  await vi.advanceTimersByTimeAsync(50);
  await result;
  expect(mocks.press).toHaveBeenCalledExactlyOnceWith(appid, "menu");
});

it.each(["NavigateToRunningApp", "m_CompositionStateStore"])("does not emit or close the menu without %s", async (property) => {
  delete mocks.router.WindowStore.GamepadUIMainWindowInstance[property];
  await expect(pressUpscalerKeyInGame("548430", "menu")).rejects.toThrow("game_focus_unavailable");
  expect(mocks.press).not.toHaveBeenCalled();
  expect(mocks.navigation.CloseSideMenus).not.toHaveBeenCalled();
});

it("rejects a stale game before navigating", async () => {
  mocks.running.mockReturnValue(null);
  await expect(pressUpscalerKeyInGame("548430", "menu")).rejects.toThrow("game_changed");
  expect(navigate).not.toHaveBeenCalled();
  expect(mocks.press).not.toHaveBeenCalled();
});


it("keeps a failed key visible through a toast and diagnostic after leaving the QAM", async () => {
  focused.Value = 548430;
  mocks.press.mockRejectedValue(new Error("transport failed with private text"));
  await expect(pressUpscalerKeyInGame("548430", "menu")).rejects.toThrow();
  expect(mocks.toast).toHaveBeenCalledWith({ title: "Panel de Control", body: "up.live.failed" });
  expect(mocks.event).toHaveBeenCalledWith("upscalers", "hotkey_error", { appid: 548430, action: "menu", stage: "key", code: "key_failed" }, false);
  expect(JSON.stringify(mocks.event.mock.calls)).not.toContain("private text");
});


it("uses the SteamUIStore composition source used by the in-game overlay", async () => {
  vi.stubGlobal("SteamUIStore", { WindowStore: mocks.router.WindowStore });
  mocks.router.WindowStore = {};
  const result = pressUpscalerKeyInGame("548430", "menu");
  focused.Value = 548430;
  await vi.advanceTimersByTimeAsync(50);
  await result;
  expect(navigate).toHaveBeenCalledWith(false);
  expect(mocks.press).toHaveBeenCalledExactlyOnceWith("548430", "menu");
});
