import { afterEach, describe, expect, it } from "vitest";

import { pollMs, setPollFactor } from "./pollCadence";

afterEach(() => setPollFactor(1));

describe("poll cadence", () => {
  it("keeps the QAM cadence by default and only ever slows down", () => {
    expect(pollMs(1000)).toBe(1000);
    setPollFactor(3);
    expect(pollMs(1000)).toBe(3000);
    setPollFactor(0.2);
    expect(pollMs(1000)).toBe(1000);
  });
});
