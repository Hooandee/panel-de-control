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
});
