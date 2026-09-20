// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

import { PowerArc } from "./PowerArc";


describe("PowerArc Steam Deck PPT scale", () => {
  afterEach(cleanup);

  it("keeps AutoTDP on its logical setpoint and hides hardware power details", () => {
    const { container } = render(
      <PowerArc
        watts={5}
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        onAc
        auto
        setpoint={5}
        appliedWatts={20}
        actualWatts={26}
        slowMarkerWatts={15}
        fastMarkerWatts={20}
      />,
    );

    expect(screen.getByText("5")).toBeTruthy();
    expect(screen.queryByText("20")).toBeNull();
    expect(screen.queryByText(/tdp\.arc\.boostHw/)).toBeNull();
    expect(screen.queryByText(/Slow/)).toBeNull();
    expect(screen.queryByText(/Fast/)).toBeNull();
    expect(container.querySelector('[data-testid="auto-tdp-halo"]')).not.toBeNull();
  });

  it("keeps a non-zero gauge and matching halo at the minimum setpoint", () => {
    const { container } = render(
      <PowerArc
        watts={5}
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        onAc
        auto
        setpoint={5}
      />,
    );

    const gauge = container.querySelector('[data-testid="auto-tdp-gauge"]')
      ?.getAttribute("stroke-dasharray");
    const halo = container.querySelector('[data-testid="auto-tdp-halo"]')
      ?.getAttribute("stroke-dasharray");
    expect(Number(gauge?.split(" ")[0])).toBeGreaterThan(0);
    expect(halo).toBe(gauge);
  });

  it("changes the automatic gauge colour as the setpoint rises", () => {
    const props = {
      watts: 10,
      limits: { min: 5, default: 15, max: 35, max_ac: 35 },
      onAc: true,
      auto: true,
    };
    const { container, rerender } = render(<PowerArc {...props} setpoint={10} />);
    const low = container.querySelector('[data-testid="auto-tdp-gauge"]')
      ?.getAttribute("stroke");

    rerender(<PowerArc {...props} setpoint={30} />);
    const high = container.querySelector('[data-testid="auto-tdp-gauge"]')
      ?.getAttribute("stroke");
    const hue = (stroke: string | null | undefined) =>
      Number(/^hsl\((\d+)/.exec(stroke ?? "")?.[1]);

    expect(hue(low)).toBeGreaterThanOrEqual(200);
    expect(hue(low)).toBeLessThanOrEqual(240);
    expect(hue(high)).toBeGreaterThanOrEqual(250);
    expect(hue(high)).toBeLessThanOrEqual(280);
  });

  it("hides charger headroom from the automatic scale", () => {
    render(
      <PowerArc
        watts={5}
        limits={{ min: 5, default: 15, max: 33, max_ac: 40 }}
        onAc
        auto
        setpoint={5}
      />,
    );

    expect(screen.getByText("40W")).toBeTruthy();
    expect(screen.queryByText("40W ⚡")).toBeNull();
  });

  it("uses the active battery ceiling for the AutoTDP scale", () => {
    render(
      <PowerArc
        watts={5}
        limits={{ min: 5, default: 15, max: 33, max_ac: 40 }}
        onAc={false}
        auto
        setpoint={5}
      />,
    );

    expect(screen.getByText("33W")).toBeTruthy();
    expect(screen.queryByText(/40W/)).toBeNull();
  });

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
    expect(screen.queryByText("tdp.arc.overclocked")).toBeNull();
  });

  it("shows an overclocked pill for a configured Steam Deck baseline", () => {
    render(
      <PowerArc
        watts={25}
        limits={{ min: 3, default: 12, max: 25, max_ac: 25 }}
        onAc
        auto
        overclocked
      />,
    );

    expect(screen.getByText("tdp.arc.overclocked")).toBeTruthy();
  });

  it("leaves a small gap between the overclock pill and the zone label", () => {
    render(
      <PowerArc
        watts={15}
        limits={{ min: 3, default: 12, max: 25, max_ac: 25 }}
        onAc
        overclocked
      />,
    );

    expect(screen.getByText("tdp.zone.balanced").style.marginTop).toBe("3px");
  });

  it("does not overlap the requested marker with the identical minimum label", () => {
    render(
      <PowerArc
        watts={3}
        limits={{ min: 3, default: 15, max: 33, max_ac: 40 }}
        onAc
        appliedWatts={5}
      />,
    );

    expect(screen.getByText("5")).toBeTruthy();
    expect(screen.getAllByText("3W")).toHaveLength(1);
  });

  it("keeps live hardware boost on its own readable line", () => {
    const { container } = render(
      <PowerArc
        watts={15}
        limits={{ min: 5, default: 15, max: 35, max_ac: 35 }}
        onAc
        actualWatts={25}
      />,
    );

    expect(screen.getByText("15")).toBeTruthy();
    expect(screen.getByText("+10 W · tdp.arc.boostHw")).toBeTruthy();
    expect(screen.queryByText("⁺10")).toBeNull();
    expect(container.querySelector('[data-testid="auto-tdp-halo"]')).toBeNull();
  });
});
