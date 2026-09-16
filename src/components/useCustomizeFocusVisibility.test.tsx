// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useCustomizeFocusVisibility } from "./useCustomizeFocusVisibility";

function Editor() {
  const ref = useCustomizeFocusVisibility();
  return <div ref={ref}><button>First</button><button>Last</button></div>;
}

describe("customization focus visibility", () => {
  let frames: Map<number, FrameRequestCallback>;
  let nextFrame: number;

  beforeEach(() => {
    frames = new Map();
    nextFrame = 0;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      frames.set(++nextFrame, callback);
      return nextFrame;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => { frames.delete(id); });
  });

  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  function control(name: string) {
    const node = screen.getByRole("button", { name });
    node.scrollIntoView = vi.fn();
    return node;
  }

  function flush() {
    const pending = [...frames.values()];
    frames.clear();
    for (const callback of pending) callback(0);
  }

  it("scrolls only the latest focused control and leaves focus outside the editor alone", () => {
    render(<><Editor /><button>Outside</button></>);
    const first = control("First");
    const last = control("Last");
    first.focus();
    last.focus();
    expect(frames.size).toBe(1);
    flush();
    expect(first.scrollIntoView).not.toHaveBeenCalled();
    expect(last.scrollIntoView).toHaveBeenCalledWith({ block: "nearest", inline: "nearest", behavior: "instant" });

    first.focus();
    screen.getByRole("button", { name: "Outside" }).focus();
    flush();
    expect(first.scrollIntoView).not.toHaveBeenCalled();
  });

  it("cancels pending work and cannot scroll a closed editor", () => {
    const { unmount } = render(<Editor />);
    const first = control("First");
    first.focus();
    const callback = [...frames.values()][0];
    unmount();
    expect(frames.size).toBe(0);
    callback(0);
    expect(first.scrollIntoView).not.toHaveBeenCalled();
  });

  it.each([
    { edge: "top", scale: 1, overflow: "hidden", expected: 84 },
    { edge: "top", scale: 2, overflow: "hidden", expected: 84 },
    { edge: "bottom", scale: 2, overflow: "auto", expected: 116 },
    { edge: "middle", scale: 1, overflow: "auto", expected: 100 },
    { edge: "top", scale: 1, overflow: "visible", expected: 100 },
  ] as const)("preserves the halo at $edge with scale $scale and overflow $overflow", ({ edge, scale, overflow, expected }) => {
    render(<div data-testid="viewport" style={{ overflowY: overflow }}><Editor /></div>);
    const viewport = screen.getByTestId("viewport");
    Object.defineProperties(viewport, {
      clientHeight: { value: 200 }, scrollHeight: { value: 600 },
      offsetHeight: { value: 202 }, clientTop: { value: 1 },
    });
    viewport.scrollTop = 100;
    viewport.getBoundingClientRect = () => new DOMRect(0, 20, 400 * scale, 202 * scale);
    const first = control("First");
    const offset = edge === "top" ? 0 : edge === "bottom" ? 170 : 80;
    first.getBoundingClientRect = () => new DOMRect(0, 20 + (1 + offset) * scale, 30 * scale, 30 * scale);
    first.focus();
    flush();
    expect(viewport.scrollTop).toBe(expected);
  });

  it.each([false, true])("restores individual margins and priorities after scrolling (failure: %s)", (fails) => {
    render(<Editor />);
    const first = control("First");
    first.style.setProperty("scroll-margin-block-start", "23px", "important");
    first.style.color = "red";
    let marginsDuringScroll: string[] = [];
    first.scrollIntoView = vi.fn(() => {
      marginsDuringScroll = [
        first.style.getPropertyValue("scroll-margin-block-start"),
        first.style.getPropertyValue("scroll-margin-block-end"),
      ];
      if (fails) throw new Error("Document cannot scroll");
    });
    first.focus();
    expect(flush).not.toThrow();
    expect(first.scrollIntoView).toHaveBeenCalledOnce();
    expect(marginsDuringScroll).toEqual(["16px", "16px"]);
    expect(first.style.getPropertyValue("scroll-margin-block-start")).toBe("23px");
    expect(first.style.getPropertyPriority("scroll-margin-block-start")).toBe("important");
    expect(first.style.getPropertyValue("scroll-margin-block-end")).toBe("");
    expect(first.style.color).toBe("red");

    const last = control("Last");
    last.focus();
    flush();
    expect(last.style.getPropertyValue("scroll-margin-block-start")).toBe("");
    expect(last.style.getPropertyValue("scroll-margin-block-end")).toBe("");
  });
});
