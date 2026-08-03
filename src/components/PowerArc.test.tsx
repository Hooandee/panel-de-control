// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

import { PowerArc } from "./PowerArc";


describe("PowerArc Steam Deck PPT scale", () => {
  afterEach(cleanup);

  it("shows Slow as the hero while keeping base and Fast markers distinct", () => {
    render(
      <PowerArc
        watts={15}
        limits={{ min: 3, default: 12, max: 15, max_ac: 15 }}
        onAc
        appliedWatts={29}
        visualMax={30}
        baseMarkerWatts={15}
        fastMarkerWatts={30}
      />,
    );

    expect(screen.getByText("29")).toBeTruthy();
    expect(screen.getAllByText("15W").length).toBeGreaterThan(0);
    expect(screen.getByText("Fast 30 W")).toBeTruthy();
    expect(screen.getByText("30W")).toBeTruthy();
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
