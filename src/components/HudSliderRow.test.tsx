// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  SliderField: ({ showValue, className }: { showValue?: boolean; className?: string }) => (
    <div
      data-testid="slider"
      data-show-value={String(showValue)}
      className={className}
    />
  ),
}));

import { HudSliderRow } from "./HudSliderRow";

describe("HudSliderRow", () => {
  afterEach(cleanup);

  it("stacks a formatted value above a compact, guttered track", () => {
    render(
      <HudSliderRow
        label="Opacity"
        value={65}
        min={0}
        max={100}
        step={5}
        unit="percent"
        onChange={() => {}}
      />,
    );

    expect(screen.getByText("65%")).toBeTruthy();
    const track = document.querySelector("[data-hud-slider-track]") as HTMLElement;
    expect(track.style.width).toBe("100%");
    expect(track.style.minWidth).toBe("0");
    expect(track.style.boxSizing).toBe("border-box");
    expect(track.style.transform).toBe("");
    const row = document.querySelector("[data-hud-slider-row]") as HTMLElement;
    expect(row.style.gap).toBe("4px");
    expect(screen.getByTestId("slider").getAttribute("data-show-value")).toBe("false");
    expect(screen.getByTestId("slider").className).toBe("pdc-hud-slider");
  });
});
