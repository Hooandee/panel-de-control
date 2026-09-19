// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CleanerActionTray } from "./CleanerActionTray";

let anchorTop: number;
let viewportBottom: number;

beforeEach(() => {
  anchorTop = 900;
  viewportBottom = 550;
  vi.spyOn(window, "innerHeight", "get").mockReturnValue(720);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.id.startsWith("quickaccess_content_")) return new DOMRect(44, 50, 300, viewportBottom - 50);
    if (this.dataset.cleanerAction === "anchor") return new DOMRect(60, anchorTop, 268, 80);
    if (this.dataset.cleanerAction === "tray") return new DOMRect(60, anchorTop, 268, 64);
    return new DOMRect();
  });
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

const mount = () => render(<div id="quickaccess_content_123"><CleanerActionTray><button>Clean</button></CleanerActionTray></div>);

describe("Cleaner footer action", () => {
  it("floats a single action inside QAM when the footer is below the visible area", () => {
    mount();
    const button = screen.getByRole("button", { name: "Clean" });
    const tray = button.parentElement!;
    expect(tray.style.position).toBe("fixed");
    expect(tray.style.left).toBe("60px");
    expect(tray.style.width).toBe("268px");
    expect(tray.style.bottom).toBe("186px");
    expect(screen.getAllByRole("button", { name: "Clean" })).toHaveLength(1);
  });

  it("returns the same focused button to its reserved footer space when scrolled to the end", () => {
    mount();
    const button = screen.getByRole("button", { name: "Clean" });
    button.focus();
    anchorTop = 450;
    fireEvent.scroll(window);
    const tray = button.parentElement!;
    expect(tray.style.position).toBe("relative");
    expect(tray.style.bottom).toBe("");
    expect(tray.parentElement!.style.height).toBe("64px");
    expect(tray.parentElement!.style.paddingBottom).toBe("16px");
    expect(document.activeElement).toBe(button);
    expect(screen.getByRole("button", { name: "Clean" })).toBe(button);
  });

  it("keeps a short list inline and starts floating if the visible panel shrinks", () => {
    anchorTop = 450;
    mount();
    const tray = screen.getByRole("button").parentElement!;
    expect(tray.style.position).toBe("relative");
    viewportBottom = 480;
    fireEvent.resize(window);
    expect(tray.style.position).toBe("fixed");
    expect(tray.style.bottom).toBe("256px");
  });

  it("stops tracking panel movement when unmounted", () => {
    vi.useFakeTimers();
    const { unmount } = mount();
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
