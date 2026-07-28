// @vitest-environment happy-dom
import { HTMLAttributes, ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  setModel: vi.fn(),
}));

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
            { kind: "metric", id: "battery" },
            { kind: "metric", id: "battery_watt" },
            { kind: "separator", id: "separator-test" },
            { kind: "spacer", id: "spacer-test", size: "small" },
          ],
        },
        values: {},
        catalog: ["fps", "ram", "battery", "battery_watt", "time"],
        presets: { essentials: ["fps"] },
      },
      setModel: mocks.setModel,
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
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

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

  it("shows the required battery base as checked and non-focusable", () => {
    render(<HudSection />);

    fireEvent.click(
      screen.getByText("copy:hud.group.battery").closest("[data-testid='focusable']")!,
    );

    const required = screen
      .getByText("copy:hud.block.base.battery")
      .closest("[data-hud-required-metric]");
    expect(required?.getAttribute("aria-checked")).toBe("true");
    expect(required?.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByText("copy:hud.block.required")).toBeTruthy();
    expect(required?.closest("[data-testid='focusable']")).toBeNull();
    expect(
      screen.getByText("copy:hud.metric.battery_watt").closest("[data-testid='focusable']"),
    ).not.toBeNull();
  });

  it("presents one general size and optional refinements by text type", () => {
    render(<HudSection />);

    fireEvent.click(screen.getByText("copy:hud.style").closest("[data-testid='focusable']")!);
    expect(screen.getByText("copy:hud.size.general")).toBeTruthy();

    fireEvent.click(
      screen.getByText("copy:hud.size.refine").closest("[data-testid='focusable']")!,
    );
    expect(screen.getByText("copy:hud.size.main")).toBeTruthy();
    expect(screen.getByText("copy:hud.size.secondary")).toBeTruthy();
    expect(screen.getByText("copy:hud.size.text")).toBeTruthy();
  });

  it("adds a metric with one complete model update", () => {
    render(<HudSection />);

    fireEvent.click(screen.getByText("copy:hud.add").closest("[data-testid='focusable']")!);
    fireEvent.click(
      screen.getByText("copy:hud.metric.time").closest("[data-testid='focusable']")!,
    );

    expect(mocks.setModel).toHaveBeenCalledTimes(1);
  });
});
