import { describe, expect, it } from "vitest";
import { ecoBrightness } from "./eco";

describe("ecoBrightness", () => {
  it("is the wake level when active, the floor when idle", () => {
    expect(ecoBrightness(true, 45, 0)).toBe(45);
    expect(ecoBrightness(false, 45, 0)).toBe(0);
  });
});
