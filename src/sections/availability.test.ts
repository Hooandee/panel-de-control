import { describe, expect, it } from "vitest";

import { allBlocksHidden } from "./availability";

describe("desktop power visibility", () => {
  const blocks = { power: { order: [], hidden: ["desktopPower"] } };

  it("treats power as modular only in desktop mode", () => {
    expect(allBlocksHidden("power", blocks, ["desktopPower"], true)).toBe(true);
    expect(allBlocksHidden("power", blocks, ["desktopPower"], false)).toBe(false);
  });

  it("ignores stale handheld presence ids when desktop mode is active", () => {
    expect(allBlocksHidden("power", blocks, ["gpu", "autoTdp"], true)).toBe(true);
  });

  it("does not let an empty handheld cache hide desktop power", () => {
    expect(allBlocksHidden("power", { power: { order: [], hidden: [] } }, [], true)).toBe(false);
  });
});
