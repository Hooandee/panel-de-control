// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../src/i18n", () => ({ useI18n: () => ({ t: (key: string) => key, lang: "en" }) }));

import type { ColoresState } from "./deckMath";
import { LightsDialog, LightsTile } from "./Lights";
import type { ColoresControl } from "./steam";

afterEach(cleanup);

const state: ColoresState = {
  power: true,
  brightness: 128,
  mode: "effect",
  color: { r: 10, g: 132, b: 255 },
  gradient: [],
  effect: { id: "rainbow", speed: 40, useGradient: false },
  capabilities: { color: true, zones: 4, maxBrightness: 255, supportedEffects: ["breathing", "rainbow", "wave", "cycle"] },
};

function control(patch: Partial<ColoresControl> = {}): ColoresControl {
  return {
    installed: true,
    state,
    setPower: vi.fn(async () => {}),
    patch: vi.fn(async () => {}),
    install: vi.fn(async () => true),
    ...patch,
  };
}

describe("lights", () => {
  it("offers to install Colores when it is missing", () => {
    const colores = control({ installed: false, state: null });
    render(<LightsDialog colores={colores} onError={vi.fn()} />);
    fireEvent.click(screen.getByText("kiosk.lights.install"));
    expect(colores.install).toHaveBeenCalled();
  });

  it("only lists the device's effects and keeps speed when switching", () => {
    const colores = control();
    render(<LightsDialog colores={colores} onError={vi.fn()} />);
    expect(screen.queryByText("kiosk.lights.effect.aurora")).toBeNull();
    fireEvent.click(screen.getByText("kiosk.lights.effect.wave"));
    expect(colores.patch).toHaveBeenCalledWith(
      { mode: "effect", effect: { id: "wave", speed: 40, use_gradient: false } },
      { mode: "effect", effect: { id: "wave", speed: 40, useGradient: false } },
    );
  });

  it("turns the lights on before switching mode from off", () => {
    const colores = control({ state: { ...state, power: false } });
    render(<LightsDialog colores={colores} onError={vi.fn()} />);
    fireEvent.click(screen.getByText("kiosk.lights.mode.solid"));
    expect(colores.setPower).toHaveBeenCalledWith(true);
    expect(colores.patch).toHaveBeenCalledWith({ mode: "solid" }, { mode: "solid", power: true });
  });

  it("summarises the lit mode and brightness on the tile", () => {
    render(<LightsTile colores={control()} onPress={vi.fn()} />);
    expect(screen.getByText("kiosk.lights.effect.rainbow · 50 %")).toBeTruthy();
  });
});
