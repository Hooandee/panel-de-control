// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const captured = vi.hoisted(() => ({ modal: null as React.ReactNode }));

vi.mock("@decky/ui", () => ({
  DialogButton: ({ children }: any) => <button>{children}</button>,
  Focusable: ({ children }: any) => <div>{children}</div>,
  ModalRoot: ({ children }: any) => <div>{children}</div>,
  showModal: (modal: React.ReactNode) => {
    captured.modal = modal;
  },
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

vi.mock("./FocusRoot", () => ({
  FocusRoot: ({ children }: any) => <div>{children}</div>,
}));

import { openAutoTdpNoticeModal } from "./AutoTdpNoticeModal";

afterEach(() => {
  cleanup();
  captured.modal = null;
});

it("keeps the experimental status visible before enabling AutoTDP", () => {
  openAutoTdpNoticeModal({ onConfirm: vi.fn(), onCancel: vi.fn() });
  render(captured.modal);

  expect(screen.getByText("tdp.auto.experimental")).toBeTruthy();
});
