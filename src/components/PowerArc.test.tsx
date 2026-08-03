// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

import { PowerArc } from "./PowerArc";


describe("PowerArc Steam Deck PPT scale", () => {
  afterEach(cleanup);

  it("keeps the sustained TDP as the hero and labels the Slow and Fast rails", () => {
    render(
      <PowerArc
        watts={15}
        limits={{ min: 3, default: 12, max: 15, max_ac: 15 }}
        onAc
        visualMax={30}
        slowMarkerWatts={29}
        fastMarkerWatts={30}
      />,
    );

    expect(screen.getByText("15")).toBeTruthy();
    expect(screen.getByText("Slow ≤ 29 W")).toBeTruthy();
    expect(screen.getByText("Fast ≤ 30 W")).toBeTruthy();
    expect(screen.getByText("30W")).toBeTruthy();
    expect(screen.getByText("tdp.arc.target")).toBeTruthy();
  });

  it("marks requested PPT rails as targets when no physical readback exists", () => {
    render(
      <PowerArc
        watts={29}
        limits={{ min: 3, default: 12, max: 15, max_ac: 15 }}
        onAc
        visualMax={30}
        appliedWatts={null}
        baseMarkerWatts={15}
        slowMarkerWatts={29}
        fastMarkerWatts={30}
      />,
    );

    expect(screen.getByText("tdp.arc.target")).toBeTruthy();
    expect(screen.getByText("Slow ≤ 29 W")).toBeTruthy();
    expect(screen.getByText("Fast ≤ 30 W")).toBeTruthy();
  });

  it("keeps the normal ceiling when no visual override exists", () => {
    render(
      <PowerArc
        watts={15}
        limits={{ min: 3, default: 12, max: 15, max_ac: 15 }}
        onAc
      />,
    );

    expect(screen.getByText("15W")).toBeTruthy();
    expect(screen.queryByText(/Fast/)).toBeNull();
  });
});
