// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarqueeText } from "./MarqueeText";

describe("MarqueeText responsive overflow", () => {
  let boxWidth = 100;
  let textWidth = 50;
  let resize: ResizeObserverCallback;
  const cancel = vi.fn();
  const animate = vi.fn(() => ({ cancel }));

  beforeEach(() => {
    boxWidth = 100;
    textWidth = 50;
    cancel.mockClear();
    animate.mockClear();
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(() => boxWidth);
    vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockImplementation(() => textWidth);
    Object.defineProperty(HTMLElement.prototype, "animate", { configurable: true, value: animate });
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: ResizeObserverCallback) { resize = callback; }
      observe() {}
      disconnect() {}
      unobserve() {}
    });
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));
  });

  afterEach(() => {
    cleanup();
    delete (HTMLElement.prototype as any).animate;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("centers fitting text and remeasures when either text or container width changes", () => {
    render(<MarqueeText text="Personalizado" alignWhenFits="center" />);

    const text = screen.getByText("Personalizado");
    const box = text.parentElement as HTMLElement;
    expect(box.style.textAlign).toBe("center");
    expect(animate).not.toHaveBeenCalled();

    textWidth = 140;
    resize([], {} as ResizeObserver);
    expect(box.style.textAlign).toBe("left");
    expect(animate).toHaveBeenCalledTimes(1);

    boxWidth = 80;
    resize([], {} as ResizeObserver);
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(animate).toHaveBeenCalledTimes(2);
  });

  it("uses a static ellipsis instead of animation when reduced motion is requested", () => {
    textWidth = 140;
    vi.mocked(matchMedia).mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as any);

    render(<MarqueeText text="Personalizado" alignWhenFits="center" />);

    const text = screen.getByText("Personalizado");
    expect(animate).not.toHaveBeenCalled();
    expect(text.style.maxWidth).toBe("100%");
    expect(text.style.overflow).toBe("hidden");
    expect(text.style.textOverflow).toBe("ellipsis");
  });
});
