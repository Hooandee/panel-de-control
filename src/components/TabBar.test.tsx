// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { forwardRef, type HTMLAttributes, type ReactNode } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement> & {
    children?: ReactNode;
    onActivate?: () => void;
  }>(({ children, onActivate: _onActivate, ...props }, ref) => (
    <div ref={ref} {...props}>{children}</div>
  )),
}));

import { TabBar } from "./TabBar";

describe("TabBar", () => {
  beforeAll(() => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(cleanup);

  it("exposes the selected tab through a stable semantic state", () => {
    render(
      <TabBar
        tabs={[
          { id: "system", icon: <span />, label: "System" },
          { id: "themes", icon: <span />, label: "Themes" },
        ]}
        activeId="themes"
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Themes").getAttribute("aria-current")).toBe("page");
    expect(screen.getByLabelText("System").hasAttribute("aria-current")).toBe(false);
  });
});
