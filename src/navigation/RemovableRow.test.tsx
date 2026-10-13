// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { forwardRef, type HTMLAttributes } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const focus = vi.hoisted(() => vi.fn(() => true));
vi.mock("../themes/runtime/navigationAccess", () => ({ createThemeNavigationAccess: () => ({ focus }) }));
vi.mock("@decky/ui", () => ({
  Focusable: forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement> & { "flow-children"?: string }>(
    ({ children, "flow-children": flow, ...props }, ref) => <div ref={ref} className="Focusable" data-flow={flow} {...props}>{children}</div>,
  ),
}));

import { RemovableRow } from "./RemovableRow";

const List = ({ rows }: { rows: string[] }) => (
  <div className="pdc-root">
    <div className="Focusable" aria-label="Añadir" />
    {rows.map((row) => (
      <RemovableRow key={row} aria-label={row}>
        <div className={`Focusable${row === "B" ? " gpfocus" : ""}`} aria-label={`Quitar ${row}`} />
      </RemovableRow>
    ))}
  </div>
);

describe("RemovableRow", () => {
  afterEach(() => {
    cleanup();
    focus.mockClear();
  });

  it("is a row focus group", () => {
    render(<List rows={["A"]} />);
    expect(screen.getByLabelText("A").getAttribute("data-flow")).toBe("row");
  });

  it("hands focus to the row above when the focused row is deleted", async () => {
    const view = render(<List rows={["A", "B"]} />);
    const above = screen.getByLabelText("Quitar A");

    view.rerender(<List rows={["A"]} />);
    await new Promise((resolve) => setTimeout(resolve, 120));

    expect(focus).toHaveBeenCalledWith(above);
  });
});
