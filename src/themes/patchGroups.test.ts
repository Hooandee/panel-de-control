import { describe, expect, it } from "vitest";

import type { CssLoaderPatch } from "./cssLoaderTypes";
import { groupThemePatches } from "./patchGroups";

function patch(name: string): CssLoaderPatch {
  return { name, defaultValue: "No", value: "No", options: ["No", "Yes"], type: "checkbox", rawType: "checkbox" };
}

describe("groupThemePatches", () => {
  it("organizes known controls and keeps unmatched controls visible", () => {
    const groups = groupThemePatches([
      patch("Cover grid columns"),
      patch("Animated transitions"),
      patch("Reduced blur performance"),
      patch("Navigation compatibility"),
      patch("Accent color"),
    ]);

    expect(groups.map((group) => [group.id, group.patches.map((item) => item.name)]))
      .toEqual([
        ["appearance", ["Accent color"]],
        ["grid", ["Cover grid columns"]],
        ["animations", ["Animated transitions"]],
        ["performance", ["Reduced blur performance"]],
        ["compatibility", ["Navigation compatibility"]],
      ]);
  });

  it("gathers every Hooandee theme's section toggles at the end", () => {
    const groups = groupThemePatches([
      patch("Estilizar Inicio"),
      patch("Posición de la parrilla"),
      patch("Estilizar QAM y Decky"),
    ], "hooandee-luminous-atlas");

    expect(groups[groups.length - 1]).toEqual({
      id: "sections",
      patches: [patch("Estilizar Inicio"), patch("Estilizar QAM y Decky")],
    });
  });

  it("does not treat a third-party theme's toggles as sections", () => {
    const groups = groupThemePatches([patch("Estilizar Inicio")], "someone-else");

    expect(groups.map((group) => group.id)).toEqual(["appearance"]);
  });
});
