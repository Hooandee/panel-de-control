// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  getUiPrefs: vi.fn(async () => ({})),
  setUiPrefs: vi.fn(async () => true),
}));

import { setQamShortcutEnabled, setQamShortcutRuntime } from "../system/qamShortcut";
import { StandardDeckyContent } from "./StandardDeckyContent";

let intersectionCallback: IntersectionObserverCallback;

class FakeResizeObserver {
  observe() {}
  disconnect() {}
}

class FakeIntersectionObserver {
  constructor(callback: IntersectionObserverCallback) {
    intersectionCallback = callback;
  }
  observe() {}
  disconnect() {}
}

function showFallbackPanel(): void {
  const host = screen.getByTestId("qam-panel-gate");
  const rect = { width: 268, height: 1 } as DOMRect;
  vi.spyOn(host, "getBoundingClientRect").mockReturnValue(rect);
  act(() => intersectionCallback([{
    target: host,
    time: 0,
    rootBounds: null,
    boundingClientRect: rect,
    intersectionRect: rect,
    isIntersecting: true,
    intersectionRatio: 1,
  }], {} as IntersectionObserver));
}

describe("StandardDeckyContent", () => {
  beforeEach(() => {
    setQamShortcutEnabled(true);
    setQamShortcutRuntime(true, true);
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    window.ResizeObserver = FakeResizeObserver as unknown as typeof ResizeObserver;
    window.IntersectionObserver = FakeIntersectionObserver as unknown as typeof IntersectionObserver;
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("keeps the full plugin available from the standard Decky entry when the shortcut is registered", () => {
    render(
      <StandardDeckyContent lifecycle={new AbortController().signal}>
        <div data-testid="fallback-panel" />
      </StandardDeckyContent>,
    );

    showFallbackPanel();
    expect(screen.getByTestId("fallback-panel")).toBeTruthy();
  });

  it("shows the standard panel when the direct tab is disabled", () => {
    setQamShortcutEnabled(false);
    setQamShortcutRuntime(false, false);

    render(
      <StandardDeckyContent lifecycle={new AbortController().signal}>
        <div data-testid="fallback-panel" />
      </StandardDeckyContent>,
    );

    showFallbackPanel();
    expect(screen.getByTestId("fallback-panel")).toBeTruthy();
  });

  it("shows the standard panel when visibility observers are unavailable", () => {
    window.ResizeObserver = undefined as unknown as typeof ResizeObserver;
    window.IntersectionObserver = undefined as unknown as typeof IntersectionObserver;
    setQamShortcutRuntime(true, false);

    render(
      <StandardDeckyContent lifecycle={new AbortController().signal}>
        <div data-testid="fallback-panel" />
      </StandardDeckyContent>,
    );

    expect(screen.getByTestId("fallback-panel")).toBeTruthy();
  });

  it("unmounts fallback content when the Decky panel becomes hidden", () => {
    const fallbackLifecycle = new AbortController();

    render(
      <StandardDeckyContent lifecycle={fallbackLifecycle.signal}>
        <div data-testid="fallback-panel" />
      </StandardDeckyContent>,
    );

    showFallbackPanel();
    expect(screen.getByTestId("fallback-panel")).toBeTruthy();

    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    fireEvent(document, new Event("visibilitychange"));

    expect(screen.queryByTestId("fallback-panel")).toBeNull();
  });
});
