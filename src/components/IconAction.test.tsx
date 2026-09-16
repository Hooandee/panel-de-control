// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { HTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate, onClick, ...props }: {
    children: ReactNode;
    onActivate?: () => void;
  } & HTMLAttributes<HTMLDivElement>) => (
    <div
      {...props}
      data-testid="focusable"
      onClick={(event) => {
        onActivate?.();
        onClick?.(event);
      }}
    >
      {children}
    </div>
  ),
}));

import { IconAction } from "./IconAction";

describe("IconAction", () => {
  afterEach(cleanup);

  it("handles Decky's activate and click pair once", () => {
    const onTap = vi.fn();
    render(<IconAction label="Subir" color="#fff" onTap={onTap}>↑</IconAction>);

    fireEvent.click(screen.getByTestId("focusable"));

    expect(onTap).toHaveBeenCalledOnce();
  });

  it("keeps a disabled action out of the focus tree", () => {
    render(<IconAction label="Subir" color="#fff" disabled onTap={() => {}}>↑</IconAction>);

    expect(screen.queryByTestId("focusable")).toBeNull();
  });
});
