import { describe, it, expect } from "vitest";
import { parse } from "./compose";
import { buildLaunchOptions, detectSelections, pillVisible } from "./catalog";
import { CustomVarDef, validateCustomVar, customVarToPill } from "./customVars";

const env = (over: Partial<CustomVarDef> = {}): CustomVarDef => ({
  id: "a", name: "Mi FPS", kind: "env", envName: "DXVK_FRAME_RATE", envValue: "60", ...over,
});
const arg = (over: Partial<CustomVarDef> = {}): CustomVarDef => ({
  id: "j", name: "Sin joystick", kind: "arg", arg: "-nojoy", ...over,
});

describe("validateCustomVar", () => {
  it("accepts a valid env var", () => {
    expect(validateCustomVar(env())).toBeNull();
  });

  it("accepts a valid arg", () => {
    expect(validateCustomVar(arg())).toBeNull();
  });

  it("rejects a blank visible name", () => {
    expect(validateCustomVar(env({ name: "   " }))).not.toBeNull();
  });

  it("rejects an invalid env NAME (bad chars / leading digit)", () => {
    expect(validateCustomVar(env({ envName: "1BAD NAME" }))).not.toBeNull();
    expect(validateCustomVar(env({ envName: "HAS-DASH" }))).not.toBeNull();
  });

  it("rejects an empty env NAME", () => {
    expect(validateCustomVar(env({ envName: "" }))).not.toBeNull();
  });

  it("rejects an empty arg flag", () => {
    expect(validateCustomVar(arg({ arg: "" }))).not.toBeNull();
  });

  it("accepts an env with empty value (bare KEY=)", () => {
    expect(validateCustomVar(env({ envValue: "" }))).toBeNull();
  });
});

describe("customVarToPill", () => {
  it("prefixes the id with custom: and carries the raw user label", () => {
    const p = customVarToPill(env({ id: "abc", name: "Límite FPS" }));
    expect(p.id).toBe("custom:abc");
    expect(p.label).toBe("Límite FPS");
    expect(p.section).toBe("advanced");
    expect(p.subgroup).toBe("params.sub.custom");
    expect(p.kind).toBe("env");
    expect(p.envName).toBe("DXVK_FRAME_RATE");
  });

  it("an env custom var applies its fixed value and is detected, preserving foreign content", () => {
    const catalog = [customVarToPill(env({ id: "abc" }))];
    expect(detectSelections(parse("DXVK_FRAME_RATE=60 %command%"), catalog)["custom:abc"]).toBe(true);
    expect(buildLaunchOptions(parse("SRM=1 %command%"), { "custom:abc": true }, catalog)).toBe(
      "SRM=1 DXVK_FRAME_RATE=60 %command%",
    );
  });

  it("does not detect the env when the value differs (honest: not our value)", () => {
    const catalog = [customVarToPill(env({ id: "abc" }))];
    expect(detectSelections(parse("DXVK_FRAME_RATE=30 %command%"), catalog)["custom:abc"]).toBeUndefined();
  });

  it("a custom arg adds and detects its flag", () => {
    const catalog = [customVarToPill(arg({ id: "j" }))];
    expect(buildLaunchOptions(parse("%command%"), { "custom:j": true }, catalog)).toBe("%command% -nojoy");
    expect(detectSelections(parse("%command% -nojoy"), catalog)["custom:j"]).toBe(true);
  });
});

describe("pillVisible exempts custom vars from PROTON_ gating", () => {
  it("a custom PROTON_ env shows even if the build doesn't list the var", () => {
    const p = customVarToPill(env({ id: "z", envName: "PROTON_WHATEVER", envValue: "1" }));
    expect(pillVisible(p, [], "rdna3")).toBe(true);
  });
});
