// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DirectQamShortcut } from "./DirectQamShortcut";

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

function setShortcutVisibility(visible: boolean): void {
  const host = screen.getByTestId("qam-panel-gate");
  const rect = {
    left: visible ? 0 : 400,
    right: visible ? 320 : 400,
    width: visible ? 320 : 0,
    height: visible ? 600 : 0,
  } as DOMRect;
  vi.spyOn(host, "getBoundingClientRect").mockReturnValue(rect);
  act(() => intersectionCallback([{
    target: host,
    time: 0,
    rootBounds: null,
    boundingClientRect: rect,
    intersectionRect: rect,
    isIntersecting: visible,
    intersectionRatio: visible ? 1 : 0,
  }], {} as IntersectionObserver));
}

describe("DirectQamShortcut", () => {
  beforeEach(() => {
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    window.ResizeObserver = FakeResizeObserver as unknown as typeof ResizeObserver;
    window.IntersectionObserver = FakeIntersectionObserver as unknown as typeof IntersectionObserver;
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders its own visible content without navigating through Decky", () => {
    render(
      <DirectQamShortcut lifecycle={new AbortController().signal}>
        <div data-testid="direct-panel" />
      </DirectQamShortcut>,
    );

    setShortcutVisibility(true);

    expect(screen.getByTestId("direct-panel")).toBeTruthy();
  });

  it("unmounts while hidden and mounts again when its tab returns", () => {
    render(
      <DirectQamShortcut lifecycle={new AbortController().signal}>
        <div data-testid="direct-panel" />
      </DirectQamShortcut>,
    );

    setShortcutVisibility(true);
    expect(screen.getByTestId("direct-panel")).toBeTruthy();
    setShortcutVisibility(false);
    expect(screen.queryByTestId("direct-panel")).toBeNull();
    setShortcutVisibility(true);
    expect(screen.getByTestId("direct-panel")).toBeTruthy();
  });

  it("stays inert after the plugin lifecycle stops", () => {
    const lifecycle = new AbortController();
    render(
      <DirectQamShortcut lifecycle={lifecycle.signal}>
        <div data-testid="direct-panel" />
      </DirectQamShortcut>,
    );

    act(() => lifecycle.abort());
    setShortcutVisibility(true);

    expect(screen.queryByTestId("direct-panel")).toBeNull();
  });

  it("keeps the private tab inert when visibility cannot be observed", () => {
    window.ResizeObserver = undefined as unknown as typeof ResizeObserver;
    window.IntersectionObserver = undefined as unknown as typeof IntersectionObserver;

    render(
      <DirectQamShortcut lifecycle={new AbortController().signal}>
        <div data-testid="direct-panel" />
      </DirectQamShortcut>,
    );

    expect(screen.queryByTestId("direct-panel")).toBeNull();
  });
});
