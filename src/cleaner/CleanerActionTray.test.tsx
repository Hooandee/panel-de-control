// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CleanerActionTray } from "./CleanerActionTray";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("Cleaner footer action", () => {
  it("sticks to the bottom of the QAM scroll instead of floating over the transformed panel", () => {
    render(<CleanerActionTray><button>Clean</button></CleanerActionTray>);
    const tray = screen.getByRole("button", { name: "Clean" }).parentElement!;
    expect(tray.style.position).toBe("sticky");
    expect(tray.style.bottom).toBe("16px");
  });

  it("reserves its height as scroll padding and restores it when removed", () => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      return new DOMRect(0, 0, 268, this.dataset.cleanerAction === "tray" ? 64 : 500);
    });
    const view = render(
      <div data-testid="scroller" style={{ overflowY: "auto" }}>
        <CleanerActionTray><button>Clean</button></CleanerActionTray>
      </div>,
    );
    const scroller = screen.getByTestId("scroller");
    expect(scroller.style.scrollPaddingBottom).toBe("96px");
    view.rerender(<div data-testid="scroller" style={{ overflowY: "auto" }} />);
    expect(scroller.style.scrollPaddingBottom).toBe("");
  });
});
