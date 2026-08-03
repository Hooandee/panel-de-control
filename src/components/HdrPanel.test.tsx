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
  ContainedSlider: ({ value }: { value: number }) => <div>slider:{value}</div>,
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
    expect(screen.getByText("slider:150")).toBeTruthy();
  });

  it("distinguishes an accepted HDR command from confirmed output", () => {
    render(<HdrPanel
      state={{ supported: true, enabled: true, follows_global: true, confirmation: "accepted" }}
      onChange={vi.fn()}
    />);

    expect(screen.getByText("display.hdr.accepted")).toBeTruthy();
  });
});
