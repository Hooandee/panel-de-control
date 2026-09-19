import { describe, expect, it } from "vitest";

import type { GameProfileRow } from "../api";
import { sectionLine } from "../system/gameProfileSummary";

const t = (key: string): string => key;

describe("game profile TDP summary", () => {
  it("shows the FPS target, starting TDP and user range for AutoTDP", () => {
    const row: GameProfileRow = {
      appid: "42",
      tdp: {
        pl1: 15,
        auto: true,
        target_fps: 55,
        initial_tdp: 8,
        min_tdp: 5,
        max_tdp: 14,
        follows_global: false,
      },
    };

    expect(sectionLine("tdp", row, t)?.text).toBe(
      "gameProfiles.auto · 55 FPS · tdp.auto.initial.label 8 W · tdp.auto.range.title 5–14 W",
    );
  });

  it("keeps the manual TDP summary unchanged", () => {
    const row: GameProfileRow = {
      appid: "42",
      tdp: {
        pl1: 12,
        auto: false,
        target_fps: 40,
        initial_tdp: 15,
        min_tdp: null,
        max_tdp: null,
        follows_global: false,
      },
    };

    expect(sectionLine("tdp", row, t)?.text).toBe("12 W");
  });
});
