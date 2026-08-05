// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../system/pdcStorage", () => ({
  hydratePrefs: vi.fn(),
  onPrefsHealed: vi.fn(() => () => undefined),
  prefsHydrated: () => true,
  readString: (key: string) => localStorage.getItem(key),
  writeString: (key: string, value: string) => localStorage.setItem(key, value),
}));

import { translate } from "./index";

describe("Spanish controller labels", () => {
  beforeEach(() => localStorage.setItem("panel-de-control-lang", "es"));

  it("uses mando rather than handle terminology", () => {
    expect(translate("mandos.vibration.handlesIntensity"))
      .toBe("Intensidad de los mandos");
    expect(translate("mandos.vibration.pattern.left"))
      .toBe("Patrón del mando izquierdo");
    expect(translate("mandos.vibration.pattern.right"))
      .toBe("Patrón del mando derecho");
  });

  it("explains the technical controller state card", () => {
    expect(translate("mandos.diagnostics.title"))
      .toBe("Estado técnico del mando");
    expect(translate("mandos.diagnostics.desc"))
      .toContain("qué sistema controla el mando");
  });

  it("provides compact labels for the discrete vibration rails", () => {
    expect(translate("mandos.vibration.intensityShort.off")).toBe("Sin");
    expect(translate("mandos.vibration.intensityShort.medium")).toBe("Media");
    expect(translate("mandos.vibration.patternShort.racing")).toBe("Carr.");
    expect(translate("mandos.vibration.patternShort.standard")).toBe("Est.");
    expect(translate("mandos.vibration.patternShort.spg")).toBe("Dep.");
  });

  it("warns that the HDR curve clips instead of claiming compression", () => {
    localStorage.setItem("panel-de-control-lang", "en");
    expect(translate("display.hdrSaturation.warning"))
      .toContain("clip");
  });
});
