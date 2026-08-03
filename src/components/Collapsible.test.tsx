// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onClick, style }: any) => <button type="button" onClick={onClick} style={style}>{children}</button>,
  PanelSectionRow: ({ children }: any) => <section>{children}</section>,
}));

vi.mock("../system/collapseState", () => ({
  isCollapsed: () => true,
  setCollapsed: vi.fn(),
}));

import { Collapsible } from "./Collapsible";

describe("Collapsible narrow title", () => {
  afterEach(() => {
    cleanup();
    delete (HTMLElement.prototype as any).animate;
    vi.restoreAllMocks();
  });

  it("keeps the GPU title on one marquee line when its value consumes header width", () => {
    const animate = vi.fn(() => ({ cancel: vi.fn() }));
    Object.defineProperty(HTMLElement.prototype, "animate", { configurable: true, value: animate });
    vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(140);
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(100);

    render(
      <div style={{ width: 220 }}>
        <Collapsible
          id="gpu-clock"
          icon={<span>GPU</span>}
          title="Frecuencia de GPU"
          summary="200–1600 MHz"
        >
          content
        </Collapsible>
      </div>,
    );

    const title = screen.getByText("Frecuencia de GPU");
    expect(title.style.whiteSpace).toBe("nowrap");
    expect(title.parentElement?.style.minWidth).toBe("0");
    expect(title.parentElement?.style.overflow).toBe("hidden");
    expect(animate).toHaveBeenCalledTimes(1);

    fireEvent.click(title.closest("button")!);
    expect(animate).toHaveBeenCalledTimes(2);
  });
});
