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
});
