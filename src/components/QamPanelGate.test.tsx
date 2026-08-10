// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QamPanelGate, canGateQamPanel } from "./QamPanelGate";

let resizeCallback: ResizeObserverCallback;
let observer: FakeResizeObserver;
let intersectionCallback: IntersectionObserverCallback;
let intersectionObserver: FakeIntersectionObserver;
let intersectionOptions: IntersectionObserverInit | undefined;

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

  constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
    intersectionCallback = callback;
    intersectionObserver = this;
    intersectionOptions = options;
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

function outsideViewport(target: Element, rect: DOMRect): IntersectionObserverEntry {
  return {
    target,
    time: 0,
    rootBounds: {
      left: 0,
      right: 268,
      top: 0,
      bottom: 800,
      width: 268,
      height: 800,
    } as DOMRectReadOnly,
    boundingClientRect: rect,
    intersectionRect: {
      left: 0,
      right: 0,
      top: 0,
      bottom: 0,
      width: 0,
      height: 0,
    } as DOMRectReadOnly,
    isIntersecting: false,
    intersectionRatio: 0,
  };
}

describe("QamPanelGate", () => {
  beforeEach(() => {
    setDocumentVisibility("visible");
    intersectionOptions = undefined;
    window.ResizeObserver = FakeResizeObserver as unknown as typeof ResizeObserver;
    window.IntersectionObserver = FakeIntersectionObserver as unknown as typeof IntersectionObserver;
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
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

  it("keeps mounted content when vertical scrolling moves the gate edge above the viewport", () => {
    render(
      <QamPanelGate lifecycle={new AbortController().signal}>
        <div data-testid="heavy-panel" />
      </QamPanelGate>,
    );
    const host = screen.getByTestId("qam-panel-gate");
    const rect = vi.spyOn(host, "getBoundingClientRect");
    const scrolledRect = {
      left: 0,
      right: 268,
      top: -1,
      bottom: 0,
      width: 268,
      height: 1,
    } as DOMRect;
    rect.mockReturnValue(scrolledRect);
    act(() => intersectionCallback([
      outsideViewport(host, scrolledRect),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.queryByTestId("heavy-panel")).toBeNull();

    rect.mockReturnValue({
      left: 0,
      right: 268,
      top: 0,
      bottom: 1,
      width: 268,
      height: 1,
    } as DOMRect);
    act(() => intersectionCallback([
      visibleIntersection(host),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.getByTestId("heavy-panel")).toBeTruthy();

    rect.mockReturnValue(scrolledRect);
    act(() => intersectionCallback([
      outsideViewport(host, scrolledRect),
    ], intersectionObserver as unknown as IntersectionObserver));

    expect(screen.getByTestId("heavy-panel")).toBeTruthy();
  });

  it("unmounts content that moves horizontally after being retained during vertical scroll", () => {
    vi.useFakeTimers();
    render(
      <QamPanelGate lifecycle={new AbortController().signal}>
        <div data-testid="heavy-panel" style={{ height: 1000 }} />
      </QamPanelGate>,
    );
    const host = screen.getByTestId("qam-panel-gate");
    const rect = vi.spyOn(host, "getBoundingClientRect");
    const enteringRect = {
      left: 200,
      right: 468,
      top: 0,
      bottom: 1,
      width: 268,
      height: 1,
    } as DOMRect;
    rect.mockReturnValue(enteringRect);
    act(() => intersectionCallback([{
      ...visibleIntersection(host),
      boundingClientRect: enteringRect,
      intersectionRect: {
        left: 200,
        right: 268,
        top: 0,
        bottom: 1,
        width: 68,
        height: 1,
      } as DOMRectReadOnly,
      intersectionRatio: 68 / 268,
    }], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.queryByTestId("heavy-panel")).toBeNull();
    expect(intersectionOptions?.threshold).toEqual([0, 1]);

    rect.mockReturnValue({
      left: 0,
      right: 268,
      top: 0,
      bottom: 1,
      width: 268,
      height: 1,
    } as DOMRect);
    act(() => intersectionCallback([
      visibleIntersection(host),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.getByTestId("heavy-panel")).toBeTruthy();

    const scrolledRect = {
      left: 0,
      right: 268,
      top: -1,
      bottom: 0,
      width: 268,
      height: 1,
    } as DOMRect;
    rect.mockReturnValue(scrolledRect);
    act(() => intersectionCallback([
      outsideViewport(host, scrolledRect),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.getByTestId("heavy-panel")).toBeTruthy();

    const hiddenRect = {
      left: 268,
      right: 536,
      top: -1,
      bottom: 0,
      width: 268,
      height: 1,
    } as DOMRect;
    rect.mockReturnValue(hiddenRect);
    act(() => vi.advanceTimersByTime(1000));

    expect(screen.queryByTestId("heavy-panel")).toBeNull();
    expect(vi.getTimerCount()).toBe(0);

    rect.mockReturnValue({
      left: 0,
      right: 268,
      top: 0,
      bottom: 1,
      width: 268,
      height: 1,
    } as DOMRect);
    act(() => intersectionCallback([
      visibleIntersection(host),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.getByTestId("heavy-panel")).toBeTruthy();
  });

  it("keeps settled bounds when content resizes during a partial tab exit", () => {
    vi.useFakeTimers();
    render(
      <QamPanelGate lifecycle={new AbortController().signal}>
        <div data-testid="heavy-panel" />
      </QamPanelGate>,
    );
    const host = screen.getByTestId("qam-panel-gate");
    const rect = vi.spyOn(host, "getBoundingClientRect");
    rect.mockReturnValue({
      left: 0,
      right: 268,
      top: 0,
      bottom: 1,
      width: 268,
      height: 1,
    } as DOMRect);
    act(() => intersectionCallback([
      visibleIntersection(host),
    ], intersectionObserver as unknown as IntersectionObserver));

    const exitingRect = {
      left: 200,
      right: 468,
      top: 0,
      bottom: 1,
      width: 268,
      height: 1,
    } as DOMRect;
    rect.mockReturnValue(exitingRect);
    act(() => intersectionCallback([{
      ...visibleIntersection(host),
      boundingClientRect: exitingRect,
      intersectionRect: {
        left: 200,
        right: 268,
        top: 0,
        bottom: 1,
        width: 68,
        height: 1,
      } as DOMRectReadOnly,
      intersectionRatio: 68 / 268,
    }], intersectionObserver as unknown as IntersectionObserver));
    act(() => resizeCallback([], observer as unknown as ResizeObserver));

    const hiddenRect = {
      left: 268,
      right: 536,
      top: 0,
      bottom: 1,
      width: 268,
      height: 1,
    } as DOMRect;
    rect.mockReturnValue(hiddenRect);
    act(() => intersectionCallback([
      outsideViewport(host, hiddenRect),
    ], intersectionObserver as unknown as IntersectionObserver));
    act(() => vi.advanceTimersByTime(1000));

    expect(screen.queryByTestId("heavy-panel")).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("unmounts children when the QAM document becomes hidden", () => {
    vi.useFakeTimers();
    render(
      <QamPanelGate lifecycle={new AbortController().signal}>
        <div data-testid="heavy-panel" />
      </QamPanelGate>,
    );
    const host = screen.getByTestId("qam-panel-gate");
    vi.spyOn(host, "getBoundingClientRect").mockReturnValue({
      left: 0,
      right: 268,
      top: 0,
      bottom: 1,
      width: 268,
      height: 1,
    } as DOMRect);
    act(() => resizeCallback([], observer as unknown as ResizeObserver));
    act(() => intersectionCallback([
      visibleIntersection(host),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.getByTestId("heavy-panel")).toBeTruthy();

    const scrolledRect = {
      left: 0,
      right: 268,
      top: -1,
      bottom: 0,
      width: 268,
      height: 1,
    } as DOMRect;
    vi.spyOn(host, "getBoundingClientRect").mockReturnValue(scrolledRect);
    act(() => intersectionCallback([
      outsideViewport(host, scrolledRect),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(vi.getTimerCount()).toBe(1);

    setDocumentVisibility("hidden");
    act(() => document.dispatchEvent(new Event("visibilitychange")));

    expect(screen.queryByTestId("heavy-panel")).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("makes a materialized panel inert when its plugin lifecycle ends", () => {
    vi.useFakeTimers();
    const lifecycle = new AbortController();
    render(
      <QamPanelGate lifecycle={lifecycle.signal}>
        <div data-testid="heavy-panel" />
      </QamPanelGate>,
    );
    const host = screen.getByTestId("qam-panel-gate");
    vi.spyOn(host, "getBoundingClientRect").mockReturnValue({
      left: 0,
      right: 268,
      top: 0,
      bottom: 1,
      width: 268,
      height: 1,
    } as DOMRect);
    act(() => intersectionCallback([
      visibleIntersection(host),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(screen.getByTestId("heavy-panel")).toBeTruthy();

    const scrolledRect = {
      left: 0,
      right: 268,
      top: -1,
      bottom: 0,
      width: 268,
      height: 1,
    } as DOMRect;
    vi.spyOn(host, "getBoundingClientRect").mockReturnValue(scrolledRect);
    act(() => intersectionCallback([
      outsideViewport(host, scrolledRect),
    ], intersectionObserver as unknown as IntersectionObserver));
    expect(vi.getTimerCount()).toBe(1);

    act(() => lifecycle.abort());

    expect(screen.queryByTestId("heavy-panel")).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
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
