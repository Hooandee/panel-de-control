import { describe, expect, it } from "vitest";

import { labelsForPatch, parseThemePatchLabels } from "./themePatchLabels";

const labels = parseThemePatchLabels({
  "Posición de la parrilla": {
    name: { en: "Grid position", "pt-BR": "Posição da grade" },
    values: { Alta: { en: "Top" } },
  },
});

describe("theme patch labels", () => {
  it("names a patch and its options in the Panel language", () => {
    const patch = labelsForPatch(labels, "Posición de la parrilla", "en");

    expect(patch.name).toBe("Grid position");
    expect(patch.option("Alta")).toBe("Top");
    expect(labelsForPatch(labels, "Posición de la parrilla", "pt-BR").name).toBe("Posição da grade");
  });

  it("falls back to the internal name for a missing language, patch or option", () => {
    expect(labelsForPatch(labels, "Posición de la parrilla", "de").name).toBe("Posición de la parrilla");
    expect(labelsForPatch(labels, "Posición de la parrilla", "en").option("Baja")).toBe("Baja");
    expect(labelsForPatch(labels, "Otra", "en").name).toBe("Otra");
  });

  it("drops malformed entries instead of trusting them", () => {
    const parsed = parseThemePatchLabels({
      Good: { name: { en: "Good" } },
      Bad: { name: { en: 3, it: "Buono" }, values: { A: { fr: "a" }, B: { de: "b" } } },
      Worse: "nope",
    });

    expect(labelsForPatch(parsed, "Good", "en").name).toBe("Good");
    expect(labelsForPatch(parsed, "Bad", "en").name).toBe("Bad");
    expect(labelsForPatch(parsed, "Bad", "it").name).toBe("Buono");
    expect(labelsForPatch(parsed, "Bad", "de").option("B")).toBe("b");
    expect(labelsForPatch(parsed, "Worse", "en").name).toBe("Worse");
    expect(parseThemePatchLabels(null)).toEqual({});
  });
});
