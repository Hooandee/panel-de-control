// @vitest-environment happy-dom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const discovery = vi.hoisted(() => ({ controls: {} as Record<string, unknown> }));
vi.mock("@decky/ui", () => ({
  findModuleByExport: () => discovery.controls, findModuleExport: () => undefined,
  Focusable: ({children}: {children: import("react").ReactNode}) => <div>{children}</div>,
  PanelSectionRow: ({children}: {children: import("react").ReactNode}) => <div>{children}</div>,
}));
vi.mock("../i18n", () => ({useI18n: () => ({t: (key: string) => key})}));
vi.mock("../system/collapseState", () => ({isCollapsed: () => false, setCollapsed: vi.fn()}));
vi.mock("../system/uiEvents", () => ({ recordUiEvent: vi.fn() }));

import { resetSteamPerformanceRuntimeCache } from "./performanceRuntime";
import { useSteamPerformanceSurface } from "./useSteamPerformanceSurface";

beforeEach(() => { vi.useFakeTimers(); resetSteamPerformanceRuntimeCache(); discovery.controls = {}; });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  delete (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore;
});

it("preserves Steam's game profile on mount, scope changes and polling", () => {
  let active = "42";
  const write = vi.fn((enabled: boolean) => { active = enabled ? "42" : "769"; });
  Object.assign(window, { SystemPerfStore: {
    msgLimits: {}, nCurrentGameID: "42",
    get nActiveProfileGameID() { return active; },
    SetGameSpecificProfileEnabled: write,
  } });
  const { rerender, unmount } = renderHook(
    ({ scope }: { scope: "global" | "game" }) => useSteamPerformanceSurface(scope, 42),
    { initialProps: { scope: "global" as "global" | "game" } },
  );
  expect(active).toBe("42");
  rerender({ scope: "game" });
  active = "769";
  act(() => vi.advanceTimersByTime(2000));
  expect(active).toBe("769");
  rerender({ scope: "global" });
  active = "42";
  act(() => vi.advanceTimersByTime(4000));
  expect(active).toBe("42");
  expect(write).not.toHaveBeenCalled();
  unmount();
});
