import { describe, expect, it } from "vitest";

import { blockOrder } from "./manifest";

describe("section block ownership", () => {
  it("places GPU frequency in System instead of Power", () => {
    expect(blockOrder("power")).not.toContain("gpu");
    expect(blockOrder("system")).toContain("gpu");
  });
});
