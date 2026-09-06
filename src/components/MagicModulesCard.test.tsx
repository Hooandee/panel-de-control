// @vitest-environment happy-dom
import { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const decky = vi.hoisted(() => ({ modal: null as ReactNode | null, showCount: 0 }));

vi.mock("@decky/ui", () => ({
  DialogButton: ({ children, onClick, disabled }: { children?: ReactNode; onClick?: () => void; disabled?: boolean }) => (
    <button disabled={disabled} onClick={onClick}>{children}</button>
  ),
  showModal: (node: ReactNode) => {
    decky.modal = node;
    decky.showCount += 1;
  },
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

vi.mock("./ConfirmDialog", () => ({
  ConfirmDialog: ({ onConfirm }: { onConfirm: () => void }) => (
    <button onClick={onConfirm}>confirm-action</button>
  ),
}));

import { MagicModulesCard } from "./MagicModulesCard";

const state = {
  supported: true,
  source: "hhd" as const,
  left: "connected" as const,
  right: "disconnected" as const,
  power: true,
  busy: false,
};

describe("MagicModulesCard", () => {
  afterEach(() => {
    decky.modal = null;
    decky.showCount = 0;
    cleanup();
  });

  it("shows each physical side and only enables safe targets", () => {
    render(<MagicModulesCard modules={state} pending={null} result={null} onAction={vi.fn()} />);

    expect(screen.getByText("mandos.modules.state.connected")).toBeTruthy();
    expect(screen.getByText("mandos.modules.state.disconnected")).toBeTruthy();
    expect(screen.getByRole("button", { name: "mandos.modules.eject.left" })).not.toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "mandos.modules.eject.right" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "mandos.modules.eject.both" })).toHaveProperty("disabled", true);
  });

  it("requires confirmation and opens only one modal for a double activation", () => {
    const onAction = vi.fn();
    render(<MagicModulesCard modules={state} pending={null} result={null} onAction={onAction} />);

    const eject = screen.getByRole("button", { name: "mandos.modules.eject.left" });
    fireEvent.click(eject);
    fireEvent.click(eject);

    expect(decky.showCount).toBe(1);
    expect(onAction).not.toHaveBeenCalled();
    render(decky.modal as ReactNode);
    fireEvent.click(screen.getByRole("button", { name: "confirm-action" }));
    expect(onAction).toHaveBeenCalledWith("eject_left");
  });

  it("reports an accepted but unconfirmed ejection honestly", () => {
    render(<MagicModulesCard
      modules={state}
      pending={null}
      result={{
        action: "eject_left",
        outcome: "unverifiable",
        accepted: true,
        reason: "state_not_changed",
        modules: state,
        config: {} as never,
      }}
      onAction={vi.fn()}
    />);

    expect(screen.getByRole("status").textContent).toBe("mandos.modules.result.unverifiable");
    expect(screen.queryByText("mandos.modules.result.confirmed")).toBeNull();
  });
});
