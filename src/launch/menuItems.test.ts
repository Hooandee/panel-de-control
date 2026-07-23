import { describe, expect, it } from "vitest";
import { replaceMenuItem } from "./menuItems";

describe("replaceMenuItem", () => {
  it("ignores a non-array menu shape", () => {
    expect(replaceMenuItem(undefined, "pdc", { key: "pdc" }, () => false)).toBe(false);
  });

  it("removes every stale copy and inserts exactly one before Properties", () => {
    const items = [
      { key: "pdc" },
      { key: "launch" },
      { key: "pdc" },
      { key: "properties" },
    ];
    const inserted = { key: "pdc", current: true };
    expect(replaceMenuItem(items, "pdc", inserted, (item) => item.key === "properties")).toBe(true);
    expect(items).toEqual([{ key: "launch" }, inserted, { key: "properties" }]);
  });

  it("appends when Properties is absent", () => {
    const items = [{ key: "launch" }];
    const inserted = { key: "pdc" };
    expect(replaceMenuItem(items, "pdc", inserted, () => false)).toBe(true);
    expect(items).toEqual([{ key: "launch" }, inserted]);
  });
});
