// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("@decky/ui", () => ({
  SliderField: ({ showValue }: { showValue?: boolean }) => (
    <div data-testid="decky-slider" data-show-value={String(showValue)} />
  ),
}));

import { DesktopPowerSlider } from "./DesktopPowerSlider";

describe("DesktopPowerSlider", () => {
  afterEach(cleanup);

  it("keeps Decky's intrinsic slider layout inside an isolated desktop row", () => {
    render(
      <DesktopPowerSlider
        label="Límite gráfico"
        value={110}
        min={18}
        max={110}
        onChange={() => {}}
      />,
    );

    const viewport = screen.getByTestId("desktop-slider-viewport");
    const layout = screen.getByTestId("desktop-slider-layout");
    const group = screen.getByTestId("desktop-slider-group");
    expect(group.style.paddingInline).toBe("8px");
    expect(group.style.boxSizing).toBe("border-box");
    expect(viewport.style.contain).toBe("layout paint");
    expect(viewport.style.overflow).toBe("hidden");
    expect(viewport.style.transform).toBe("");
    expect(layout.style.transform).toBe("scale(0.85)");
    expect(parseFloat(layout.style.width) * 0.85).toBeCloseTo(100, 4);
    expect(layout.style.transformOrigin).toBe("left top");
    expect(screen.getByTestId("decky-slider").dataset.showValue).toBe("false");
  });

  it("renders the current value and both endpoints in independent rows", () => {
    render(
      <DesktopPowerSlider
        label="Límite gráfico"
        value={110}
        min={18}
        max={110}
        onChange={() => {}}
      />,
    );

    expect(screen.getByText("18 W")).toBeTruthy();
    expect(screen.getAllByText("110 W")).toHaveLength(2);
  });
});
