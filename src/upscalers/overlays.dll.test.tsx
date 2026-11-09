// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ findSP: () => window }));
vi.mock("@decky/api", () => ({ routerHook: {}, callable: () => vi.fn().mockResolvedValue(null) }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../platform/overGameComposition", () => ({ OverGameComposition: () => null }));
vi.mock("../platform/qamSurface", () => ({ subscribeQamSurface: () => () => {} }));
const running = vi.hoisted(() => ({ id: 1462040 }));
vi.mock("../tdp/useRunningGame", () => ({ useRunningGame: () => ({ liveAppid: running.id }) }));
vi.mock("./gameInFront", () => ({ useGameInFront: () => true }));
vi.mock("./useOverlayLive", () => ({ useOverlayLive: vi.fn() }));
import { useOverlayLive } from "./useOverlayLive";
import { InGameBadge, publishOverview, writeInGameMode } from "./overlays";

function publish(engine = "dll", status = "not_run") {
  publishOverview({ builds: [{ id: "dll-test", engine, family: "fsr", version: "4.1.2" }],
    installs: { "1462040": { build: "dll-test", status, options: {} } } } as never);
}
function opacity() {
  return screen.getByText("FSR 4.1.2").parentElement?.parentElement?.style.opacity;
}
beforeEach(() => {
  running.id = 1462040;
  writeInGameMode("always");
  vi.mocked(useOverlayLive).mockReturnValue({ live: null, lossless: null, makoSpatial: null, makoMultiplier: null, makoResolutionWarning: false });
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.clearAllMocks(); });
it("shows an intact DLL installation without inventing live readings", () => {
  publish();
  render(<InGameBadge />);
  expect(opacity()).toBe("0.92");
  expect(screen.queryByText(/→|up.overlay.generating/)).toBeNull();
});
it.each([["dll", "broken"], ["optiscaler", "not_run"]])("keeps %s %s hidden without runtime evidence", (engine, status) => {
  publish(engine, status);
  render(<InGameBadge />);
  expect(opacity()).toBe("0");
});
it("clears the DLL pill after removal or switching games", () => {
  publish();
  const { rerender } = render(<InGameBadge />);
  expect(opacity()).toBe("0.92");
  running.id = 292030;
  rerender(<InGameBadge />);
  expect(screen.queryByText("FSR 4.1.2")).toBeNull();
  running.id = 1462040;
  rerender(<InGameBadge />);
  act(() => publishOverview({ builds: [], installs: {} } as never));
  expect(screen.queryByText("FSR 4.1.2")).toBeNull();
});
it("respects off and the start-only duration for installed DLLs", () => {
  vi.useFakeTimers();
  publish();
  writeInGameMode("off");
  render(<InGameBadge />);
  expect(opacity()).toBe("0");
  act(() => writeInGameMode("start"));
  expect(opacity()).toBe("0.92");
  act(() => vi.advanceTimersByTime(6000));
  expect(opacity()).toBe("0");
});
