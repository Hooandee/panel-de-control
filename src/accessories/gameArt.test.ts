import { describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ accessoryEvent: vi.fn(), getAccessoriesState: vi.fn() }));
vi.mock("../tdp/runningGame", () => ({ readRunningGame: vi.fn() }));

import { logoBox } from "./gameArt";

describe("logoBox", () => {
  it("fits a wide logo to the panel width and centres it", () => {
    const box = logoBox(640, 160);
    expect(box.w).toBeCloseTo(64 * 0.9);
    expect(box.x).toBeCloseTo((64 - box.w) / 2);
    expect(box.y).toBeCloseTo((54 - box.h) / 2);
  });

  it("keeps a tall logo inside the height", () => {
    const box = logoBox(300, 400);
    expect(box.h).toBeCloseTo(54 * 0.6);
    expect(box.w).toBeLessThan(64);
  });
});
