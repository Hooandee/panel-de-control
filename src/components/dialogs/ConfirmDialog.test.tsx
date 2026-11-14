// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  DialogButton: ({ children, onClick }: any) => <button onClick={onClick}>{children}</button>,
  Focusable: ({ children }: any) => <div>{children}</div>,
  ModalRoot: ({ children }: any) => <div>{children}</div>,
}));

vi.mock("../FocusRoot", () => ({ FocusRoot: ({ children }: any) => <div>{children}</div> }));

import { ConfirmDialog } from "./ConfirmDialog";

afterEach(cleanup);

const renderDialog = () => {
  const order: string[] = [];
  const onConfirm = vi.fn(() => order.push("confirm"));
  const closeModal = vi.fn(() => order.push("close"));
  render(<ConfirmDialog title="T" desc="D" confirmLabel="Yes" cancelLabel="No" onConfirm={onConfirm} closeModal={closeModal} />);
  return { order, onConfirm, closeModal };
};

it("closes before running the confirm action", () => {
  const { order } = renderDialog();
  fireEvent.click(screen.getByText("Yes"));
  expect(order).toEqual(["close", "confirm"]);
});

it("cancel only closes", () => {
  const { onConfirm, closeModal } = renderDialog();
  fireEvent.click(screen.getByText("No"));
  expect(closeModal).toHaveBeenCalledOnce();
  expect(onConfirm).not.toHaveBeenCalled();
});
