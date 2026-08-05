import { describe, expect, it } from "vitest";

import {
  PICKABLE_BLOCKS,
  SECTION_BLOCKS,
  blockOrder,
  pickableBlockIds,
} from "./manifest";

describe("controller diagnostics placement", () => {
  it("keeps diagnostics out of the normal controller layout but available to support views", () => {
    expect(SECTION_BLOCKS.mandos.map(({ id }) => id)).not.toContain("diagnostics");
    expect(PICKABLE_BLOCKS.mandos.map(({ id }) => id)).toContain("diagnostics");
  });

  it("deduplicates diagnostics persisted by an older normal layout", () => {
    const persisted = ["manager", "vibration", "diagnostics"];
    const ids = pickableBlockIds("mandos", persisted);

    expect(ids.filter((id) => id === "diagnostics")).toHaveLength(1);
  });
});

describe("section block ownership", () => {
  it("places GPU frequency in System instead of Power", () => {
    expect(blockOrder("power")).not.toContain("gpu");
    expect(blockOrder("system")).toContain("gpu");
  });
});
