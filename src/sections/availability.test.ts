import { describe, expect, it } from "vitest";

import { allBlocksHidden } from "./availability";

describe("desktop power visibility", () => {
  const blocks = { power: { order: [], hidden: ["desktopPower"] } };

  it("keeps the new always-present Steam block visible across an old presence cache", () => {
    expect(allBlocksHidden("power", blocks, ["desktopPower"], true)).toBe(false);
    expect(allBlocksHidden("power", blocks, ["desktopPower"], false)).toBe(false);
  });

  it("keeps Steam performance visible when the cache only has handheld ids", () => {
    expect(allBlocksHidden("power", blocks, ["gpu", "autoTdp"], true)).toBe(false);
  });

  it("hides desktop power only when both desktop blocks are hidden", () => {
    const hidden = { power: { order: [], hidden: ["desktopPower", "steamPerformance"] } };
    expect(allBlocksHidden("power", hidden, ["desktopPower"], true)).toBe(true);
  });

  it("does not let an empty handheld cache hide desktop power", () => {
    expect(allBlocksHidden("power", { power: { order: [], hidden: [] } }, [], true)).toBe(false);
  });
});
