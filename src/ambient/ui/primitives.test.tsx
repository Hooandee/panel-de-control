// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/api", () => ({}));
vi.mock("../../platform/preferences", () => ({ isCollapsed: () => false, setCollapsed: () => undefined }));
vi.mock("../../components/ContainedSlider", () => ({ ContainedSlider: () => null }));
vi.mock("@decky/ui", () => ({
  Dropdown: () => null, Menu: () => null, MenuItem: () => null, showContextMenu: () => undefined,
  Focusable: ({ children, onActivate, onClick, ...rest }: { children?: ReactNode; onActivate?: () => void; onClick?: () => void; [key: string]: unknown }) => (
    <div {...(rest as object)} onClick={onClick ?? onActivate}>{children}</div>
  ),
  SliderField: () => null,
  DialogButton: () => null,
}));

import { ToggleRow } from "./primitives";

afterEach(cleanup);

describe("ToggleRow", () => {
  it("is announced as a switch with its state and flips it", () => {
    const onChange = vi.fn();
    render(<ToggleRow label="Fondo personalizado" checked={false} onChange={onChange} />);
    const toggle = screen.getByRole("switch", { name: "Fondo personalizado" });
    expect(toggle.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith(true);
  });
});
