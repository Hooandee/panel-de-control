import { describe, expect, it } from "vitest";

import { coerceKioskViewIds, kioskPageViews, toggleKioskView } from "./kioskViews";

const view = (id: string, blocks: string[] = ["tdp"]) => ({ id, name: id, icon: "star" as const, blocks });

describe("kioskPageViews", () => {
  const views = [view("a"), view("b"), view("empty", []), view("c")];

  it("shows every view with blocks when none is chosen", () => {
    expect(kioskPageViews(views, []).map((v) => v.id)).toEqual(["a", "b", "c"]);
  });

  it("shows only the chosen views, in the views' own order", () => {
    expect(kioskPageViews(views, ["c", "a"]).map((v) => v.id)).toEqual(["a", "c"]);
  });

  it("ignores chosen ids of deleted or empty views", () => {
    expect(kioskPageViews(views, ["gone", "empty"]).map((v) => v.id)).toEqual(["a", "b", "c"]);
  });
});

describe("kiosk view choice", () => {
  it("toggles one view in and out", () => {
    expect(toggleKioskView(["a"], "b")).toEqual(["a", "b"]);
    expect(toggleKioskView(["a", "b"], "a")).toEqual(["b"]);
  });

  it("never trusts a corrupt stored value", () => {
    expect(coerceKioskViewIds({ a: 1 })).toEqual([]);
    expect(coerceKioskViewIds(["a", 3, null, "b"])).toEqual(["a", "b"]);
  });
});
