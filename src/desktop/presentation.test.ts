import { describe, expect, it } from "vitest";

import { clockText, dialFraction, metricText, vramView } from "./presentation";

describe("desktop presentation", () => {
  it("clamps the TGP dial to the validated range", () => {
    expect(dialFraction(55, 55, 110)).toBe(0);
    expect(dialFraction(82.5, 55, 110)).toBe(0.5);
    expect(dialFraction(120, 55, 110)).toBe(1);
    expect(dialFraction(null, 55, 110)).toBe(0);
  });

  it("names an idle or unavailable GPU clock without placeholder glyphs", () => {
    expect(clockText(0, "Reposo", "No disponible")).toBe("Reposo");
    expect(clockText(null, "Reposo", "No disponible")).toBe("No disponible");
    expect(clockText(1850, "Reposo", "No disponible")).toBe("1850 MHz");
  });

  it("formats VRAM in compact binary gigabytes", () => {
    const view = vramView(1587, 8176, "No disponible");
    expect(view.value).toBe("1.5");
    expect(view.total).toBe("8.0 GB");
    expect(view.fraction).toBeCloseTo(1587 / 8176);
    expect(vramView(null, 8176, "No disponible").value).toBe("No disponible");
  });

  it("uses explicit unavailable copy instead of an em dash", () => {
    expect(metricText(null, "W", "Sin sensor")).toBe("Sin sensor");
    expect(metricText(18.4, "W", "Sin sensor")).toBe("18.4 W");
    expect(metricText(18, "W", "Sin sensor")).toBe("18 W");
  });
});
