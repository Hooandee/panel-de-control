import { describe, expect, it } from "vitest";

import { presentThemePatchText } from "./patchPresentation";

describe("presentThemePatchText", () => {
  it("translates Obsidian's Spanish CSS Loader contract without changing its raw value", () => {
    expect(presentThemePatchText("Escena de parrilla", "en")).toBe("Grid scene");
    expect(presentThemePatchText("Abismo orbital", "en")).toBe("Orbital Abyss");
    expect(presentThemePatchText("Cinemático", "en")).toBe("Cinematic");
    expect(presentThemePatchText("Yes", "es")).toBe("Sí");
  });

  it("preserves unknown values from current or future CSS Loader themes", () => {
    expect(presentThemePatchText("Future nebula", "en")).toBe("Future nebula");
    expect(presentThemePatchText("Future nebula", "es")).toBe("Future nebula");
  });
});
