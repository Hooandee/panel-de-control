// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { forwardRef, type HTMLAttributes, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type FocusableProps = HTMLAttributes<HTMLDivElement> & {
  children?: ReactNode;
  onActivate?: () => void;
};

vi.mock("@decky/ui", () => ({
  Focusable: forwardRef<HTMLDivElement, FocusableProps>(function Focusable(
    { children, onActivate, onClick, ...props },
    ref,
  ) {
    return (
      <div
        ref={ref}
        onClick={(event) => {
          onActivate?.();
          onClick?.(event);
        }}
        {...props}
      >
        {children}
      </div>
    );
  }),
}));

vi.mock("@decky/api", () => ({ callable: () => async () => ({}) }));

import { ShellHeader } from "./ShellHeader";

describe("ShellHeader", () => {
  beforeEach(() => {
    window.localStorage.setItem("panel-de-control-lang", "es");
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it("returns exactly once through the visible back action", () => {
    const onBack = vi.fn();
    render(<ShellHeader onBack={onBack} />);

    fireEvent.click(screen.getByRole("button", { name: "Inicio" }));

    expect(onBack).toHaveBeenCalledOnce();
  });

  it("does not treat global keyboard input as a back request", () => {
    const onBack = vi.fn();
    render(<ShellHeader onBack={onBack} />);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onBack).not.toHaveBeenCalled();
  });

  it("keeps the back action compact without duplicating the controller shortcut", () => {
    render(<ShellHeader onBack={vi.fn()} />);

    const row = screen.getByTestId("detail-back-row");
    const back = screen.getByRole("button", { name: "Inicio" });
    expect(row.style.minHeight).toBe("28px");
    expect(row.style.paddingBottom).toBe("");
    expect(row.style.borderBottom).toBe("");
    expect(back.style.minHeight).toBe("28px");
    expect(within(back).queryByText("B")).toBeNull();
  });
});
