// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  PanelSectionRow: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  ToggleField: ({ label, description }: { label: string; description: string }) => (
    <div>{label}<span>{description}</span></div>
  ),
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

vi.mock("./ContainedSlider", () => ({
  ContainedSlider: ({ value, min, max, step }: {
    value: number;
    min: number;
    max: number;
    step: number;
  }) => <div data-testid="hdr-slider">slider:{value}:{min}:{max}:{step}</div>,
}));

import { HdrPanel } from "./HdrPanel";

describe("HdrPanel", () => {
  afterEach(cleanup);

  it("keeps HDR output and HDR saturation in one card", () => {
    render(<HdrPanel
      state={{ supported: true, enabled: true, actual_enabled: true, follows_global: true }}
      onChange={vi.fn()}
      saturation={{ value: 150, experimental: true, onChange: vi.fn() }}
    />);

    const hdr = screen.getByText("display.hdr");
    const saturation = screen.getByText("display.hdrSaturation");
    expect(hdr.closest("section")).toBe(saturation.closest("section"));
    expect(screen.getByText("slider:150:100:150:5")).toBeTruthy();
    expect(screen.getByText("display.hdrSaturation.desc")).toBeTruthy();
    expect(screen.getByText("device.experimental.badge")).toBeTruthy();

    const header = screen.getByTestId("hdr-saturation-header");
    expect(header.style.gridTemplateColumns).toBe("minmax(0, 1fr) auto");
    expect(screen.getByTestId("hdr-saturation-copy").style.minWidth).toBe("0");
    expect(screen.getByTestId("hdr-saturation-value").style.whiteSpace).toBe("nowrap");
  });

  it("keeps the functional description when a high value needs a warning", () => {
    render(<HdrPanel
      state={{ supported: true, enabled: true, actual_enabled: true, follows_global: true }}
      onChange={vi.fn()}
      saturation={{ value: 140, experimental: false, onChange: vi.fn() }}
    />);

    expect(screen.getByText("display.hdrSaturation.desc")).toBeTruthy();
    expect(screen.getByText("display.hdrSaturation.warning")).toBeTruthy();
  });

  it("explains that saturation is saved but not visible while HDR is disabled", () => {
    render(<HdrPanel
      state={{ supported: true, enabled: false, actual_enabled: false, follows_global: true }}
      onChange={vi.fn()}
      saturation={{ value: 140, experimental: false, onChange: vi.fn() }}
    />);

    expect(screen.getByText("display.hdrSaturation.desc")).toBeTruthy();
    expect(screen.getByText("display.hdrSaturation.inactive")).toBeTruthy();
    expect(screen.queryByText("display.hdrSaturation.warning")).toBeNull();
  });

  it("distinguishes an accepted HDR command from confirmed output", () => {
    render(<HdrPanel
      state={{ supported: true, enabled: true, follows_global: true, confirmation: "accepted" }}
      onChange={vi.fn()}
    />);

    expect(screen.getByText("display.hdr.accepted")).toBeTruthy();
  });

  it("shows the failed HDR state instead of stacking it with accepted", () => {
    render(<HdrPanel
      state={{
        supported: true,
        enabled: true,
        follows_global: true,
        last_apply: false,
        confirmation: "accepted",
      }}
      onChange={vi.fn()}
    />);

    expect(screen.getByText("display.hdr.applyFailed")).toBeTruthy();
    expect(screen.queryByText("display.hdr.accepted")).toBeNull();
  });
});
