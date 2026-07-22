import { describe, expect, it } from "vitest";
import { availableIds, registerBlock, getBlockDef, type Caps } from "./blockRegistry";
import type { DeviceInfo } from "../api";

const noop = (() => null) as any;
const dev = (key: string): DeviceInfo => ({ key } as DeviceInfo);

describe("block registry availability", () => {
  it("keeps ids without a predicate (always available)", () => {
    registerBlock("t_plain", { sectionId: "t", Component: noop });
    const caps: Caps = { device: null };
    expect(availableIds(["t_plain"], caps)).toEqual(["t_plain"]);
  });

  it("drops a block whose predicate is false, keeps it when true", () => {
    registerBlock("t_rgb", {
      sectionId: "t",
      Component: noop,
      available: ({ device }) => !!device && !device.key.startsWith("steam_deck"),
    });
    expect(availableIds(["t_rgb"], { device: dev("rog_ally") })).toEqual(["t_rgb"]);
    expect(availableIds(["t_rgb"], { device: dev("steam_deck_oled") })).toEqual([]);
    expect(availableIds(["t_rgb"], { device: null })).toEqual([]);
  });

  it("treats unknown ids as available (never drops a not-yet-registered block)", () => {
    expect(availableIds(["t_unknown"], { device: null })).toEqual(["t_unknown"]);
  });

  it("preserves input order and filters the mixed set", () => {
    expect(availableIds(["t_plain", "t_rgb", "t_unknown"], { device: dev("steam_deck_lcd") }))
      .toEqual(["t_plain", "t_unknown"]);
    expect(getBlockDef("t_rgb")?.sectionId).toBe("t");
  });
});
