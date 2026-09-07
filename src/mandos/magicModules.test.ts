import { describe, expect, it } from "vitest";

import { canEject, moduleStateKey, outcomeKey } from "./magicModules";

const modules = {
  supported: true,
  source: "hhd" as const,
  left: "connected" as const,
  right: "disconnected" as const,
  power: true,
  busy: false,
};

describe("Magic Modules presentation rules", () => {
  it("only enables actions whose target modules are connected", () => {
    expect(canEject(modules, "eject_left", null)).toBe(true);
    expect(canEject(modules, "eject_right", null)).toBe(false);
    expect(canEject(modules, "eject_both", null)).toBe(false);
  });

  it("blocks every action while either side is busy", () => {
    expect(canEject({ ...modules, busy: true }, "eject_left", null)).toBe(false);
    expect(canEject(modules, "eject_left", "eject_right")).toBe(false);
  });

  it("maps physical states and outcomes without treating acceptance as confirmation", () => {
    expect(moduleStateKey("connected")).toBe("mandos.modules.state.connected");
    expect(outcomeKey("confirmed")).toBe("mandos.modules.result.confirmed");
    expect(outcomeKey("unverifiable")).toBe("mandos.modules.result.unverifiable");
  });
});
