import { describe, expect, it } from "vitest";

import { blockOrder, CATEGORY_IDS, PINNED_TAB, TABS } from "./manifest";

describe("section block ownership", () => {
  it("places GPU frequency in System instead of Power", () => {
    expect(blockOrder("power")).not.toContain("gpu");
    expect(blockOrder("system")).toContain("gpu");
  });
});

describe("theme section registration", () => {
  it("keeps Themes customizable immediately before pinned Settings", () => {
    expect(TABS.slice(-2).map((tab) => tab.id)).toEqual(["themes", "settings"]);
    expect(CATEGORY_IDS).toContain("themes");
    expect(CATEGORY_IDS).not.toContain(PINNED_TAB);
  });
});
