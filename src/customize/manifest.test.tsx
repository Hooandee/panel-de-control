import { describe, expect, it } from "vitest";

import { blockOrder, blocksForSection, customizationBlocks } from "./manifest";

describe("section block ownership", () => {
  it("places GPU frequency in System instead of Power", () => {
    expect(blockOrder("power")).not.toContain("gpu");
    expect(blockOrder("system")).toContain("gpu");
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
