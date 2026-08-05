// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  SliderField: ({ showValue }: { showValue?: boolean }) => (
    <div data-testid="native-slider" data-show-value={String(showValue)} />
  ),
}));

import { ContainedSlider } from "./ContainedSlider";

afterEach(cleanup);

describe("ContainedSlider", () => {
  it("keeps a percentage value on one line outside Steam's compressed slider row", () => {
    render(
      <ContainedSlider
        label="Intensidad del gatillo derecho"
        value={0}
        min={0}
        max={100}
        showValue
        valueSuffix="%"
        onChange={vi.fn()}
      />,
    );

    const value = screen.getByTestId("contained-slider-value");
    expect(value.textContent).toBe("0%");
    expect(value.style.whiteSpace).toBe("nowrap");
    expect(value.style.flexShrink).toBe("0");
    expect(screen.getByTestId("native-slider").dataset.showValue).toBe("false");
  });
});
