import { describe, expect, it } from "vitest";
import { coerceViews, viewTabId, isViewTabId, DEFAULT_VIEW_ICON, providersFor } from "./views";

describe("providersFor", () => {
  const section: Record<string, string> = {
    battery: "system", brightness: "system", color: "display", hdr: "display", remap: "mandos",
  };
  const getSection = (id: string) => section[id];

  it("returns the distinct sections in input order", () => {
    expect(providersFor(["battery", "color", "hdr", "remap"], getSection)).toEqual(["system", "display", "mandos"]);
  });
  it("dedupes and skips unknown block ids", () => {
    expect(providersFor(["color", "color", "ghost", "brightness"], getSection)).toEqual(["display", "system"]);
  });
  it("empty for no blocks", () => {
    expect(providersFor([], getSection)).toEqual([]);
  });
});

describe("coerceViews", () => {
  it("keeps well-formed views and normalizes fields", () => {
    const out = coerceViews([
      { id: "a", name: "Juego", icon: "zap", blocks: ["battery", "curve"] },
      { id: "b", name: "X", icon: "star", blocks: [] },
    ]);
    expect(out).toEqual([
      { id: "a", name: "Juego", icon: "zap", blocks: ["battery", "curve"] },
      { id: "b", name: "X", icon: "star", blocks: [] },
    ]);
  });

  it("drops entries without a valid id, and non-array input", () => {
    expect(coerceViews([{ name: "no id" }, { id: "", name: "empty" }, 5, null])).toEqual([]);
    expect(coerceViews({} as unknown)).toEqual([]);
    expect(coerceViews("nope" as unknown)).toEqual([]);
  });

  it("falls back to the default icon and empty name/blocks on bad types", () => {
    expect(coerceViews([{ id: "a", name: 7, icon: "bogus", blocks: "x" }])).toEqual([
      { id: "a", name: "", icon: DEFAULT_VIEW_ICON, blocks: [] },
    ]);
  });

  it("filters non-string block ids", () => {
    expect(coerceViews([{ id: "a", blocks: ["ok", 3, null, "yes"] }])[0].blocks).toEqual(["ok", "yes"]);
  });
});

describe("view tab id helpers", () => {
  it("builds and detects a view tab id", () => {
    expect(viewTabId("abc")).toBe("view:abc");
    expect(isViewTabId("view:abc")).toBe(true);
    expect(isViewTabId("system")).toBe(false);
  });
});
