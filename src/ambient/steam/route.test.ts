import { describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ Router: {} }));

import { surfaceForPath } from "./route";

describe("surfaceForPath", () => {
  it("maps Big Picture routes", () => {
    expect(surfaceForPath("/library/home")).toBe("home");
    expect(surfaceForPath("/library")).toBe("library");
    expect(surfaceForPath("/library/tab/Installed")).toBe("library");
    expect(surfaceForPath("/library/app/730")).toBe("other");
    expect(surfaceForPath("/settings")).toBe("other");
    expect(surfaceForPath(undefined)).toBe("other");
  });
});
