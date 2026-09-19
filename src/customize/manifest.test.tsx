import { describe, expect, it } from "vitest";

import {
  blockOrder,
  blocksForSection,
  CATEGORY_IDS,
  customizationBlocks,
  pickableBlocksForSection,
  PINNED_TAB,
  subitemsFor,
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
  it("gives every tab dashboard presentation metadata", () => {
    for (const tab of TABS) {
      expect(tab.descriptionKey).toBe(`nav.${tab.id}.desc`);
      expect(tab.accent).toMatch(/^#[0-9a-f]{6}$/i);
      expect(typeof tab.icon).toBe("function");
    }
  });

  it("keeps Themes customizable immediately before pinned Settings", () => {
    expect(TABS.slice(-2).map((tab) => tab.id)).toEqual(["themes", "settings"]);
    expect(CATEGORY_IDS).toContain("themes");
    expect(CATEGORY_IDS).not.toContain(PINNED_TAB);
  });
});

describe("desktop-only customization blocks", () => {
  it("offers native Steam performance controls in both device modes", () => {
    expect(blocksForSection("power", false).map((block) => block.id)).not.toContain("desktopPower");
    expect(blocksForSection("power", true).map((block) => block.id)).toEqual([
      "desktopPower",
      "steamPerformance",
    ]);
  });

  it("places Steam's controls before Auto-TDP in the handheld default order", () => {
    expect(blocksForSection("power", false).map((block) => block.id)).toEqual([
      "steamPerformance",
      "autoTdp",
    ]);
  });

  it("allows the independent Steam block in custom views", () => {
    expect(pickableBlocksForSection("power", false, null).map((block) => block.id)).toEqual([
      "tdp",
      "steamPerformance",
      "autoTdp",
    ]);
  });

  it("keeps the desktop core visible with a stale handheld presence cache", () => {
    expect(customizationBlocks("power", true, ["autoTdp"]).map((block) => block.id))
      .toEqual(["desktopPower", "steamPerformance"]);
  });
});

describe("battery customization", () => {
  it("offers charge-limit ownership only when the backend supports it", () => {
    expect(subitemsFor("battery", false).map((item) => item.id)).toEqual(["health"]);
    expect(subitemsFor("battery", true).map((item) => item.id)).toEqual(["health", "limit"]);
    expect(subitemsFor("battery", true).find((item) => item.id === "limit")?.moduleId).toBe("chargeLimit");
  });
});
