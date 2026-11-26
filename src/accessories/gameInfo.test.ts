import { describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ accessoryEvent: vi.fn() }));

import { gameInfoFrom } from "./gameInfo";

describe("game info", () => {
  it("keeps store tags in order, play time and achievement counts", () => {
    const info = gameInfoFrom("10", { m_setStoreTags: new Set([699, 19]), minutes_playtime_forever: 125 },
      [{ bAchieved: true }, { bAchieved: false }, { bAchieved: true }]);
    expect(info).toEqual({ appid: "10", tags: [699, 19], playtime_min: 125, achievements: { done: 2, total: 3 } });
  });

  it("leaves out what Steam does not know", () => {
    expect(gameInfoFrom("7", null, null)).toEqual({ appid: "7", tags: [], playtime_min: null, achievements: null });
  });
});
