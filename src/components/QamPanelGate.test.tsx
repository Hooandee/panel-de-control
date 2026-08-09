// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QamPanelGate, canGateQamPanel } from "./QamPanelGate";

let resizeCallback: ResizeObserverCallback;
let observer: FakeResizeObserver;
let intersectionCallback: IntersectionObserverCallback;
let intersectionObserver: FakeIntersectionObserver;

class FakeResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();

  constructor(callback: ResizeObserverCallback) {
    resizeCallback = callback;
    observer = this;
  }
}

class FakeIntersectionObserver {
  observe = vi.fn();
  disconnect = vi.fn();

  constructor(callback: IntersectionObserverCallback) {
    intersectionCallback = callback;
    intersectionObserver = this;
  }
}

function setDocumentVisibility(value: DocumentVisibilityState): void {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value,
  });
}

function visibleIntersection(target: Element): IntersectionObserverEntry {
  const rect = target.getBoundingClientRect();
  return {
    target,
    time: 0,
    rootBounds: null,
    boundingClientRect: rect,
    intersectionRect: rect,
    isIntersecting: true,
    intersectionRatio: 1,
  };
}

describe("QamPanelGate", () => {
  beforeEach(() => {
    setDocumentVisibility("visible");
    window.ResizeObserver = FakeResizeObserver as unknown as typeof ResizeObserver;
    window.IntersectionObserver = FakeIntersectionObserver as unknown as typeof IntersectionObserver;
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("rejects hosts without ResizeObserver capability", () => {
    expect(canGateQamPanel({
      ResizeObserver: FakeResizeObserver,
      IntersectionObserver: FakeIntersectionObserver,
    })).toBe(true);
    expect(canGateQamPanel({ ResizeObserver: FakeResizeObserver })).toBe(false);
    expect(canGateQamPanel({ IntersectionObserver: FakeIntersectionObserver })).toBe(false);
  });

  it("mounts children only while the QAM document and panel have visible geometry", () => {
    render(
      <QamPanelGate lifecycle={new AbortController().signal}>
        <div data-testid="heavy-panel" />
      </QamPanelGate>,
    );
    const host = screen.getByTestId("qam-panel-gate");
    const rect = vi.spyOn(host, "getBoundingClientRect");

    expect(screen.queryByTestId("heavy-panel")).toBeNull();

    rect.mockReturnValue({ width: 268, height: 1 } as DOMRect);
    act(() => resizeCallback([], observer as unknown as ResizeObserver));
    expect(screen.queryByTestId("heavy-panel")).toBeNull();
    act(() => intersectionCallback([
      visibleIntersection(host),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.getByTestId("heavy-panel")).toBeTruthy();

    rect.mockReturnValue({ width: 0, height: 0 } as DOMRect);
    act(() => resizeCallback([], observer as unknown as ResizeObserver));
    expect(screen.queryByTestId("heavy-panel")).toBeNull();
  });

  it("unmounts children when the QAM document becomes hidden", () => {
    render(
      <QamPanelGate lifecycle={new AbortController().signal}>
        <div data-testid="heavy-panel" />
      </QamPanelGate>,
    );
    const host = screen.getByTestId("qam-panel-gate");
    vi.spyOn(host, "getBoundingClientRect").mockReturnValue({ width: 268, height: 1 } as DOMRect);
    act(() => resizeCallback([], observer as unknown as ResizeObserver));
    act(() => intersectionCallback([
      visibleIntersection(host),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.getByTestId("heavy-panel")).toBeTruthy();

    setDocumentVisibility("hidden");
    act(() => document.dispatchEvent(new Event("visibilitychange")));

    expect(screen.queryByTestId("heavy-panel")).toBeNull();
  });

  it("makes a materialized panel inert when its plugin lifecycle ends", () => {
    const lifecycle = new AbortController();
    render(
      <QamPanelGate lifecycle={lifecycle.signal}>
        <div data-testid="heavy-panel" />
      </QamPanelGate>,
    );
    const host = screen.getByTestId("qam-panel-gate");
    vi.spyOn(host, "getBoundingClientRect").mockReturnValue({ width: 268, height: 1 } as DOMRect);
    act(() => intersectionCallback([
      visibleIntersection(host),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.getByTestId("heavy-panel")).toBeTruthy();

    act(() => lifecycle.abort());

    expect(screen.queryByTestId("heavy-panel")).toBeNull();
    expect(observer.disconnect).toHaveBeenCalledOnce();
    expect(intersectionObserver.disconnect).toHaveBeenCalledOnce();
  });

  it("keeps an explicit fallback usable when the rendered document lacks gating", () => {
    window.IntersectionObserver = undefined as unknown as typeof IntersectionObserver;
    const lifecycle = new AbortController();
    render(
      <QamPanelGate lifecycle={lifecycle.signal} fallback={<div data-testid="fallback-panel" />}>
        <div data-testid="heavy-panel" />
      </QamPanelGate>,
    );

    expect(screen.getByTestId("fallback-panel")).toBeTruthy();
    expect(screen.queryByTestId("heavy-panel")).toBeNull();

    act(() => lifecycle.abort());
    expect(screen.queryByTestId("fallback-panel")).toBeNull();

    act(() => intersectionCallback([
      visibleIntersection(screen.getByTestId("qam-panel-gate")),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.queryByTestId("fallback-panel")).toBeNull();
  });

  it("disconnects its observer and document listener on unmount", () => {
    const remove = vi.spyOn(document, "removeEventListener");
    const rendered = render(
      <QamPanelGate lifecycle={new AbortController().signal}><div /></QamPanelGate>,
    );

    rendered.unmount();

    expect(observer.disconnect).toHaveBeenCalledOnce();
    expect(intersectionObserver.disconnect).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
  });
});
