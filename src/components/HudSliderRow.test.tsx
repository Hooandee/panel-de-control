// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  SliderField: ({ showValue }: { showValue?: boolean }) => (
    <div data-testid="slider" data-show-value={String(showValue)} />
  ),
}));

import { HudSliderRow } from "./HudSliderRow";

describe("HudSliderRow", () => {
  afterEach(cleanup);

  it("stacks a formatted value above an unscaled full-width track", () => {
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
    expect(track.style.transform).toBe("");
    expect(screen.getByTestId("slider").getAttribute("data-show-value")).toBe("false");
  });
});
