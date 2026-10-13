// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useStickyTray } from "./useStickyTray";

const Tray = () => {
  const ref = useRef<HTMLDivElement>(null);
  useStickyTray(ref);
  return <div ref={ref} role="status" />;
};

function layout(rects: Record<string, [number, number]>) {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const [top, bottom] = rects[this.dataset.testid ?? this.getAttribute("role") ?? ""] ?? [0, 0];
    return new DOMRect(0, top, 268, bottom - top);
  });
}

describe("useStickyTray", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("scrolls the focused control out from under the tray when the tray appears", () => {
    layout({ status: [380, 494], focused: [387, 418], scroller: [0, 454] });
    render(
      <div data-testid="scroller" style={{ overflowY: "auto" }}>
        <div data-testid="focused" className="Focusable gpfocus" />
        <Tray />
      </div>,
    );

    expect(screen.getByTestId("scroller").scrollTop).toBe(418 - 380 + 16);
  });

  it("leaves the scroll alone when the focused control stays visible", () => {
    layout({ status: [380, 494], focused: [100, 130], scroller: [0, 454] });
    render(
      <div data-testid="scroller" style={{ overflowY: "auto" }}>
        <div data-testid="focused" className="Focusable gpfocus" />
        <Tray />
      </div>,
    );

    expect(screen.getByTestId("scroller").scrollTop).toBe(0);
  });
});
