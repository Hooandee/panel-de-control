// @vitest-environment happy-dom
import { forwardRef } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const focus = vi.hoisted(() => vi.fn());
vi.mock("../themes/runtime/navigationAccess", () => ({ createThemeNavigationAccess: () => ({ focus }) }));
vi.mock("@decky/ui", () => ({ Focusable: forwardRef<HTMLDivElement, any>(({ onActivate, onCancel, children, ...props }, ref) => <div {...props} ref={ref} onKeyDown={e => { if (e.key === "Escape") onCancel?.(e); }}>{children}</div>) }));
import { PickerButton } from "./parts";
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const options = [{ value: "off", label: "Apagada" }, { value: "lsfg", label: "Lossless Scaling", caption: "Descripción que debe permanecer dentro de la ficha" }];
it("opens inline and returns focus on cancel without changing selection", () => {
  const change = vi.fn();
  render(<PickerButton label="Generación de frames" value="off" options={options} onChange={change} />);
  const button = screen.getByRole("button");
  fireEvent.click(button);
  expect(screen.getByRole("radiogroup")).toBeTruthy();
  fireEvent.keyDown(screen.getByRole("radio", { name: /Lossless/ }), { key: "Escape" });
  expect(screen.queryByRole("radiogroup")).toBeNull();
  expect(change).not.toHaveBeenCalled();
  expect(focus).toHaveBeenCalledWith(button);
});
it("chooses an option and closes the inline list", () => {
  const change = vi.fn();
  render(<PickerButton label="Generación de frames" value="off" options={options} onChange={change} />);
  fireEvent.click(screen.getByRole("button"));
  fireEvent.click(screen.getByRole("radio", { name: /Lossless/ }));
  expect(change).toHaveBeenCalledWith("lsfg");
  expect(screen.queryByRole("radiogroup")).toBeNull();
});
