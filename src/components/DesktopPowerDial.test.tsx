// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { DesktopPowerDial } from "./DesktopPowerDial";

describe("DesktopPowerDial", () => {
  afterEach(cleanup);

  it("keeps the small unit beside the large value and uses the short limit label", () => {
    render(
      <DesktopPowerDial
        value={110}
        min={55}
        max={110}
        label="Límite gráfico"
        unavailable="No disponible"
      />,
    );

    const valueRow = screen.getByTestId("desktop-power-dial-value");
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Límite gráfico: 110 W");
    expect(valueRow.style.display).toBe("flex");
    expect(valueRow.style.alignItems).toBe("baseline");
    expect(valueRow.contains(screen.getByText("110"))).toBe(true);
    expect(valueRow.contains(screen.getByText("W"))).toBe(true);
    expect(screen.getByText("W").style.fontSize).toBe("10px");
    expect(screen.queryByText("Límite gráfico")).toBeNull();
  });
});
