import { describe, expect, it } from "vitest";

import {
  blockOrder,
  blocksForSection,
  CATEGORY_IDS,
  customizationBlocks,
  PINNED_TAB,
  TABS,
} from "./manifest";

describe("section block ownership", () => {
  it("places GPU frequency in System instead of Power", () => {
    expect(blockOrder("power")).not.toContain("gpu");
    expect(blockOrder("system")).toContain("gpu");
  });

  it("offers AYANEO Magic Modules as a controller block", () => {
    expect(blockOrder("mandos")).toContain("magicModules");
  });
});

describe("theme section registration", () => {
  it("keeps Themes customizable immediately before pinned Settings", () => {
    expect(TABS.slice(-2).map((tab) => tab.id)).toEqual(["themes", "settings"]);
    expect(CATEGORY_IDS).toContain("themes");
    expect(CATEGORY_IDS).not.toContain(PINNED_TAB);
  });
});

describe("desktop-only customization blocks", () => {
  it("offers CPU and graphics only while desktop mode is active", () => {
    expect(blocksForSection("power", false).map((block) => block.id)).not.toContain("desktopPower");
    expect(blocksForSection("power", true).map((block) => block.id)).toEqual(["desktopPower"]);
  });

  it("does not change the handheld default order", () => {
    expect(blocksForSection("power", false).map((block) => block.id)).toEqual(["autoTdp"]);
  });

  it("keeps the desktop core visible with a stale handheld presence cache", () => {
    expect(customizationBlocks("power", true, ["autoTdp"]).map((block) => block.id))
      .toEqual(["desktopPower"]);
  });
});
