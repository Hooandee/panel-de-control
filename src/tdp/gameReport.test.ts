import { describe, expect, it } from "vitest";

import { isSameGameReport } from "./gameReport";

const report = (appid: string | null, name: string | null = null) => ({ appid, name });

describe("isSameGameReport", () => {
  it("recognises whether a late response still belongs to the current request", () => {
    expect(isSameGameReport(report("2", "B"), report("1", "A"))).toBe(false);
    expect(isSameGameReport(report("2", "B"), report("2", "B"))).toBe(true);
  });
});
