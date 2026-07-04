import { describe, expect, it } from "vitest";

import {
  currentTargetValue,
  managerDescKey,
  managerLabelKey,
  prettyTarget,
  targetToValue,
  valueToTarget,
} from "./logic";

describe("managerLabelKey / managerDescKey", () => {
  it("maps known managers", () => {
    expect(managerLabelKey("hhd")).toBe("mandos.manager.hhd");
    expect(managerLabelKey("inputplumber")).toBe("mandos.manager.ip");
    expect(managerDescKey("inputplumber")).toBe("mandos.desc.inputplumber");
  });
  it("falls back to none for anything unknown", () => {
    expect(managerLabelKey("weird")).toBe("mandos.manager.none");
    expect(managerDescKey("weird")).toBe("mandos.desc.none");
  });
});

describe("target encoding", () => {
  it("round-trips gamepad + keyboard targets", () => {
    expect(targetToValue({ gamepad: "South" })).toBe("gp:South");
    expect(targetToValue({ key: "KeyEsc" })).toBe("key:KeyEsc");
    expect(valueToTarget("gp:South")).toEqual({ gamepad: "South" });
    expect(valueToTarget("key:KeyEsc")).toEqual({ key: "KeyEsc" });
  });
  it("currentTargetValue uses the first target, or empty", () => {
    expect(currentTargetValue([{ gamepad: "North" }, { gamepad: "West" }])).toBe("gp:North");
    expect(currentTargetValue([])).toBe("");
  });
  it("prettyTarget maps face buttons + strips Key prefix, else raw", () => {
    expect(prettyTarget("gp:South")).toBe("A");
    expect(prettyTarget("gp:LeftPaddle1")).toBe("LeftPaddle1");
    expect(prettyTarget("key:KeyEsc")).toBe("Esc");
  });
});
