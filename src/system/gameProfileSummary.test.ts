import { describe, expect, it } from "vitest";

import type { GameProfileRow } from "../api";
import { sectionLine } from "./gameProfileSummary";

const t = (key: string, params?: Record<string, string | number>) => {
  if (key === "tdp.level.value") return `Level ${params?.level}`;
  if (key === "tdp.split.summary") return `CPU ${params?.cpu} · GPU ${params?.gpu}`;
  return key;
};

const row = (unit: "W" | "level"): GameProfileRow =>
  ({
    tdp: { unit, pl1: 6, auto: false, follows_global: false },
  }) as unknown as GameProfileRow;

describe("game profile power line", () => {
  it("shows watts on PC and levels on ARM", () => {
    expect(sectionLine("tdp", row("W"), t)?.text).toBe("6 W");
    expect(sectionLine("tdp", row("level"), t)?.text).toBe("Level 6");
    expect(sectionLine("tdp", {
      tdp: { unit: "level", pl1: 3, gpu_level: 10, auto: false, follows_global: false },
    } as unknown as GameProfileRow, t)?.text).toBe("CPU 3 · GPU 10");
  });
});
