// @vitest-environment happy-dom
import { forwardRef } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const focus = vi.hoisted(() => vi.fn());
vi.mock("../themes/runtime/navigationAccess", () => ({ createThemeNavigationAccess: () => ({ focus }) }));
vi.mock("@decky/ui", () => ({ Focusable: forwardRef<HTMLDivElement, any>(({ onActivate, onCancel, children, ...props }, ref) => <div {...props} ref={ref} onKeyDown={e => { if (e.key === "Escape") onCancel?.(e); if (e.key === "Enter") onActivate?.(e); }}>{children}</div>) }));
import { ActionButton, ListRow, PickerButton } from "./parts";
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const options = [{ value: "off", label: "Apagada" }, { value: "lsfg", label: "Lossless Scaling", caption: "Descripción que debe permanecer dentro de la ficha" }];
it("opens inline and returns focus on cancel without changing selection", async () => {
  const change = vi.fn();
  render(<PickerButton label="Generación de frames" value="off" options={options} onChange={change} />);
  const button = screen.getByRole("button");
  fireEvent.click(button);
  expect(screen.getByRole("radiogroup")).toBeTruthy();
  fireEvent.keyDown(screen.getByRole("radio", { name: /Lossless/ }), { key: "Escape" });
  expect(screen.queryByRole("radiogroup")).toBeNull();
  expect(change).not.toHaveBeenCalled();
  await waitFor(() => expect(focus).toHaveBeenCalledWith(button));
});
it("chooses an option and closes the inline list", () => {
  const change = vi.fn();
  render(<PickerButton label="Generación de frames" value="off" options={options} onChange={change} />);
  fireEvent.click(screen.getByRole("button"));
  fireEvent.click(screen.getByRole("radio", { name: /Lossless/ }));
  expect(change).toHaveBeenCalledWith("lsfg");
  expect(screen.queryByRole("radiogroup")).toBeNull();
});

it("moves focus to the selected option after opening with the controller", async () => {
  render(<PickerButton label="Flujo" showLabel value="lsfg" options={options} onChange={vi.fn()} />);
  fireEvent.keyDown(screen.getByRole("button", { name: "Flujo" }), { key: "Enter" });
  const selected = screen.getByRole("radio", { name: /Lossless/ });
  await waitFor(() => expect(focus).toHaveBeenCalledWith(selected));
  expect(selected.getAttribute("aria-checked")).toBe("true");
});
it("restores focus only after the chosen option has unmounted", async () => {
  const change = vi.fn();
  render(<PickerButton label="Flujo" value="off" options={options} onChange={change} />);
  const trigger = screen.getByRole("button");
  fireEvent.keyDown(trigger, { key: "Enter" });
  const selected = screen.getByRole("radio", { name: /Lossless/ });
  await waitFor(() => expect(focus).toHaveBeenCalled());
  focus.mockClear();
  fireEvent.keyDown(selected, { key: "Enter" });
  expect(selected.isConnected).toBe(false);
  expect(focus).not.toHaveBeenCalled();
  await waitFor(() => expect(focus).toHaveBeenCalledWith(trigger));
  expect(change).toHaveBeenCalledOnce();
});
it("keeps activation handlers while blocked and does not invoke actions", () => {
  const action = vi.fn();
  const { container, rerender } = render(<ActionButton label="Aplicar" onPress={action} busy />);
  fireEvent.keyDown(container.firstChild!, { key: "Enter" });
  expect(action).not.toHaveBeenCalled();
  rerender(<ActionButton label="Aplicar" onPress={action} />);
  fireEvent.keyDown(container.firstChild!, { key: "Enter" });
  expect(action).toHaveBeenCalledOnce();
  rerender(<ListRow label="Modo" onPress={action} disabled />);
  fireEvent.keyDown(container.firstChild!, { key: "Enter" });
  expect(action).toHaveBeenCalledOnce();
});
it("does not open a disabled picker", () => {
  render(<PickerButton label="Flujo" value="off" options={options} onChange={vi.fn()} disabled />);
  fireEvent.keyDown(screen.getByRole("button"), { key: "Enter" });
  expect(screen.queryByRole("radiogroup")).toBeNull();
});
