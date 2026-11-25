import { describe, expect, it } from "vitest";

import type { GameProfileRow } from "../api";
import { sectionLine } from "./gameProfileSummary";

const t = (key: string, params?: Record<string, string | number>) =>
  key === "tdp.level.value" ? `Level ${params?.level}` : key;

const row = (unit: "W" | "level"): GameProfileRow =>
  ({
    tdp: { unit, pl1: 6, auto: false, follows_global: false },
  }) as unknown as GameProfileRow;

describe("game profile power line", () => {
  it("shows watts on PC and levels on ARM", () => {
    expect(sectionLine("tdp", row("W"), t)?.text).toBe("6 W");
    expect(sectionLine("tdp", row("level"), t)?.text).toBe("Level 6");
  });
});

describe("game profile HUD line", () => {
  it("lists a game's own HUD as on or off", () => {
    const on = { appid: "1", hud: { enabled: true, follows_global: false } } as GameProfileRow;
    const off = { appid: "1", hud: { enabled: false, follows_global: true } } as GameProfileRow;
    expect(sectionLine("hud", on, t)).toEqual({
      label: "gameProfiles.sec.hud", text: "gameProfiles.hudOn", dim: false,
    });
    expect(sectionLine("hud", off, t)).toEqual({
      label: "gameProfiles.sec.hud", text: "gameProfiles.hudOff", dim: true,
    });
  });
});
