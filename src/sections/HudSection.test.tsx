// @vitest-environment happy-dom
import { HTMLAttributes, ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({
    children,
    onActivate,
    onClick,
    ...props
  }: {
    children?: ReactNode;
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
  PanelSectionRow: ({ children }: { children: ReactNode }) => (
    <div data-panel-section-row>{children}</div>
  ),
  ToggleField: ({ label }: { label: string }) => <div>{label}</div>,
  TextField: ({ label }: { label: string }) => <div>{label}</div>,
  SliderField: ({ label }: { label?: string }) => <div>{label}</div>,
  Spinner: () => <span>spinner</span>,
  showModal: vi.fn(),
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => `copy:${key}` }),
}));

vi.mock("../mangohud/useHud", async () => {
  const { DEFAULT_MODEL } = await vi.importActual<typeof import("../mangohud/model")>(
    "../mangohud/model",
  );
  return {
    useHud: () => ({
      state: {
        supported: true,
        running: true,
        capability: "ready",
        applyStatus: "applied",
        model: {
          ...DEFAULT_MODEL,
          items: [
            { kind: "metric", id: "fps" },
            { kind: "metric", id: "ram" },
            { kind: "separator", id: "separator-test" },
            { kind: "spacer", id: "spacer-test", size: "small" },
          ],
        },
        values: {},
        catalog: ["fps", "ram"],
        presets: { essentials: ["fps"] },
      },
      setModel: vi.fn(),
      setEnabled: vi.fn(),
      reload: vi.fn(),
      reloadStatus: "idle",
      saveStatus: "idle",
      reset: vi.fn(),
    }),
  };
});

vi.mock("../system/collapseState", () => ({
  isCollapsed: () => true,
  setCollapsed: vi.fn(),
}));

vi.mock("../components/HudPreview", () => ({
  HudPreview: () => <div>preview</div>,
}));

vi.mock("../components/ColorPicker", () => ({
  ColorPicker: ({ label }: { label: string }) => <span>{label}</span>,
}));

vi.mock("../components/ConfirmDialog", () => ({
  ConfirmDialog: () => <div>confirm</div>,
}));

import { HudSection } from "./HudSection";

describe("HudSection QAM composition", () => {
  afterEach(cleanup);

  it("uses one bounded stack and only exposes editors on configurable rows", () => {
    render(<HudSection />);

    expect(screen.getAllByTestId("hud-stack")).toHaveLength(1);
    expect(document.querySelectorAll("[data-panel-section-row]")).toHaveLength(1);
    expect(screen.getByText("copy:hud.metric.fps").closest("[aria-expanded]")).not.toBeNull();
    expect(screen.getByText("copy:hud.metric.ram").closest("[aria-expanded]")).toBeNull();
    expect(screen.getByText("copy:hud.elem.separator").closest("[aria-expanded]")).toBeNull();
    expect(
      screen
        .getByText("copy:hud.elem.spacer · copy:hud.spacer.small")
        .closest("[aria-expanded]"),
    ).not.toBeNull();
  });

  it("keeps the add trigger mounted while the picker opens", () => {
    render(<HudSection />);

    const trigger = screen.getByText("copy:hud.add").closest("[data-testid='focusable']");
    expect(trigger).not.toBeNull();

    fireEvent.click(trigger!);

    expect(screen.getByText("copy:hud.close").closest("[data-testid='focusable']")).toBe(trigger);
  });
});
