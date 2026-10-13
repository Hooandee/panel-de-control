// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate: _onActivate, ...props }: { children: ReactNode; onActivate?: () => void; [key: string]: unknown }) => (
    <button {...props}>{children}</button>
  ),
  PanelSectionRow: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));

import { OledLookCard } from "./OledLookCard";

describe("OledLookCard", () => {
  afterEach(cleanup);

  it("keeps the native button mounted while there is nothing to undo, so focus is never dropped", () => {
    const onReset = vi.fn();
    const view = render(<OledLookCard active onApply={vi.fn()} onReset={onReset} />);
    const native = screen.getByText("display.native");
    fireEvent.click(native);
    expect(onReset).toHaveBeenCalledOnce();

    view.rerender(<OledLookCard active={false} onApply={vi.fn()} onReset={onReset} />);
    expect(screen.getByText("display.native")).toBe(native);
    expect(native.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(native);
    expect(onReset).toHaveBeenCalledOnce();
  });
});
