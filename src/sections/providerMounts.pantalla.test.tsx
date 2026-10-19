// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const color = vi.hoisted(() => ({
  state: { supported: true },
  scope: "global",
  game: null,
  revertIn: null as number | null,
  saving: false,
  confirmCalibration: vi.fn(),
  discardCalibration: vi.fn(),
}));

type ShortcutProps = {
  children: ReactNode;
  onSecondaryButton?: () => void;
  onOptionsButton?: () => void;
  onSecondaryActionDescription?: ReactNode;
  onOptionsActionDescription?: ReactNode;
};

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onSecondaryButton, onOptionsButton, onSecondaryActionDescription, onOptionsActionDescription }: ShortcutProps) => (
    <div data-testid="shortcuts">
      {onSecondaryButton && <button onClick={onSecondaryButton}>X {onSecondaryActionDescription}</button>}
      {onOptionsButton && <button onClick={onOptionsButton}>Y {onOptionsActionDescription}</button>}
      {children}
    </div>
  ),
  PanelSectionRow: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../display/useColor", () => ({ useColor: () => color }));
vi.mock("../display/useHdr", () => ({ useHdr: () => ({}) }));
vi.mock("../display/useNight", () => ({ useNight: () => ({}) }));
vi.mock("../display/color", () => ({ isNativeColor: () => true }));
vi.mock("../mandos/useController", () => ({ useController: () => ({}) }));
vi.mock("../tdp/useTdp", () => ({ useTdp: () => ({}) }));
vi.mock("../tdp/useTdpConflict", () => ({ useTdpConflict: () => ({}) }));
vi.mock("../customize/modules", () => ({ useModules: () => new Set<string>(), setModuleDisabled: vi.fn() }));
vi.mock("../customize/moduleLogic", () => ({ effectiveEnabled: () => true }));
vi.mock("../api", () => ({ setSeenTdpConflictTakeover: vi.fn() }));
vi.mock("../components/TdpConflictModal", () => ({ openTdpConflictModal: vi.fn() }));

import { PantallaProviderMount } from "./providerMounts";

describe("PantallaProviderMount gamepad shortcuts", () => {
  afterEach(() => {
    color.revertIn = null;
    color.saving = false;
    color.confirmCalibration.mockReset();
    color.discardCalibration.mockReset();
    cleanup();
  });

  it("offers no X/Y actions without a pending preview", () => {
    render(<PantallaProviderMount><div>blocks</div></PantallaProviderMount>);

    expect(screen.queryByText(/^X /)).toBeNull();
    expect(screen.queryByText(/^Y /)).toBeNull();
    expect(screen.getByText("blocks")).toBeTruthy();
  });

  it("saves with X and discards with Y while a preview is pending", () => {
    color.revertIn = 12;
    render(<PantallaProviderMount><div>blocks</div></PantallaProviderMount>);

    screen.getByText("X display.confirm.save").click();
    screen.getByText("Y display.confirm.discard").click();

    expect(color.confirmCalibration).toHaveBeenCalledOnce();
    expect(color.discardCalibration).toHaveBeenCalledOnce();
  });

  it("withdraws the shortcuts while the save is in flight", () => {
    color.revertIn = 12;
    color.saving = true;
    render(<PantallaProviderMount><div>blocks</div></PantallaProviderMount>);

    expect(screen.queryByText(/^X /)).toBeNull();
  });
});
