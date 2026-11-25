import { describe, expect, it } from "vitest";

import { snapMove } from "./composerSnap";

const pill = { x: 10, y: 10, w: 20, h: 9 };
const star = { x: 40, y: 10, w: 9, h: 8 };

describe("magnetic moves", () => {
  it("moves freely away from anything to stick to", () => {
    expect(snapMove([{ x: 20, y: 20, w: 5, h: 5 }], 0, 1, 0)).toEqual({ x: 21, y: 20, guideX: null, guideY: null });
  });

  it("jumps flush against a neighbour when close, tetris style", () => {
    const moved = snapMove([pill, { ...star, x: 33 }], 1, -1, 0);
    expect(moved.x).toBe(30);
    expect(moved.guideX).toBe(30);
  });

  it("aligns top edges with a neighbour", () => {
    const moved = snapMove([pill, { ...star, y: 12, h: 9 }], 1, 0, -1);
    expect(moved.y).toBe(10);
    expect(moved.guideY).toBe(10);
  });

  it("sticks to the display edges and centre", () => {
    expect(snapMove([{ x: 2, y: 30, w: 6, h: 6 }], 0, -1, 0).x).toBe(0);
    expect(snapMove([{ x: 25, y: 30, w: 10, h: 6 }], 0, 1, 0).x).toBe(27);
  });

  it("leaves a snap behind when pushed on", () => {
    const moved = snapMove([pill, { ...star, x: 30 }], 1, 1, 0);
    expect(moved.x).toBe(31);
  });

  it("keeps at least one column on the display", () => {
    expect(snapMove([{ x: -40, y: 0, w: 41, h: 5 }], 0, -1, 0).x).toBe(-40);
  });
});
