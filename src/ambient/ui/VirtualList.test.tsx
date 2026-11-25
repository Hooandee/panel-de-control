// @vitest-environment happy-dom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { HTMLAttributes, FocusEventHandler } from "react";

import { VirtualList } from "./VirtualList";

vi.mock("@decky/ui", async () => {
  const { forwardRef } = await import("react");
  const flows = new Set(["column", "column-reverse", "row", "row-reverse", "grid", "geometric"]);
  type Props = HTMLAttributes<HTMLDivElement> & { onGamepadFocus?: FocusEventHandler<HTMLDivElement>; "flow-children"?: string };
  return { Focusable: forwardRef<HTMLDivElement, Props>(({ onGamepadFocus, "flow-children": flow, ...props }, ref) => {
    if (flow !== undefined && !flows.has(flow)) throw new Error(`Unhandled flow-children: ${flow}`);
    return <div {...props} ref={ref} data-navigation-flow={flow} onFocus={onGamepadFocus} />;
  }) };
});

const items = Array.from({ length: 500 }, (_, i) => `s${i}`);

describe("VirtualList", () => {
  afterEach(cleanup);

  it("keeps only the visible window in the DOM", () => {
    const { container } = render(<VirtualList items={items} rowHeight={56} height={280} keyOf={(s) => s} renderRow={(s) => <span>{s}</span>} />);
    expect(container.querySelectorAll("span").length).toBeLessThan(20);
    expect(container.textContent).toContain("s0");
    expect(container.textContent).not.toContain("s200");
  });

  it("moves the window on scroll and asks for more near the end", () => {
    const more = vi.fn();
    const { container } = render(<VirtualList items={items.slice(0, 40)} rowHeight={56} height={280} keyOf={(s) => s} renderRow={(s) => <span>{s}</span>} onEndReached={more} />);
    const scroller = container.firstElementChild as HTMLDivElement;
    scroller.scrollTop = 56 * 30;
    fireEvent.scroll(scroller);
    expect(container.textContent).toContain("s35");
    expect(more).toHaveBeenCalled();
  });

  it("keeps the next controller destination mounted while progressing beyond the initial window and back", () => {
    const { container, getByRole, queryByRole } = render(<VirtualList controllerNavigation items={items} rowHeight={56} height={280} keyOf={(s) => s} renderRow={(s) => <button>{s}</button>} />);
    const scroller = container.firstElementChild as HTMLDivElement;
    expect(scroller.dataset.navigationFlow).toBe("column");
    expect(queryByRole("button", { name: "s75" })).toBeNull();

    for (let index = 0; index <= 75; index += 1) {
      fireEvent.focus(getByRole("button", { name: `s${index}` }));
      expect(scroller.scrollTop).toBe(Math.max(0, (index + 1) * 56 - 280));
      expect(container.querySelectorAll("button").length).toBeLessThan(20);
    }
    expect(queryByRole("button", { name: "s0" })).toBeNull();

    for (let index = 74; index >= 0; index -= 1) {
      fireEvent.focus(getByRole("button", { name: `s${index}` }));
      expect(scroller.scrollTop).toBe(Math.min(71, index) * 56);
      expect(container.querySelectorAll("button").length).toBeLessThan(20);
    }
    expect(queryByRole("button", { name: "s75" })).toBeNull();
  });

  it("does not scroll or extend the window on focus without controller navigation", () => {
    const { container, getByRole, queryByRole } = render(<VirtualList items={items} rowHeight={56} height={280} keyOf={(s) => s} renderRow={(s) => <button>{s}</button>} />);
    const scroller = container.firstElementChild as HTMLDivElement;
    const initialCount = container.querySelectorAll("button").length;
    fireEvent.focus(getByRole("button", { name: "s10" }));
    expect(scroller.dataset.navigationFlow).toBeUndefined();
    expect(scroller.scrollTop).toBe(0);
    expect(container.querySelectorAll("button").length).toBe(initialCount);
    expect(queryByRole("button", { name: "s12" })).toBeNull();
  });
});
