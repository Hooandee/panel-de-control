import { describe, it, expect } from "vitest";
import { parse } from "./compose";
import { buildLaunchOptions, detectSelections, pillVisible } from "./catalog";
import {
  CustomVarDef,
  validateCustomVar,
  customVarToPill,
  customPillVisible,
  sanitizeCustomVars,
  saveCustomDraft,
  retireCustomVar,
} from "./customVars";

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

describe("validateCustomVar duplicate detection", () => {
  it("rejects an env whose NAME is already taken (base catalog or another custom)", () => {
    expect(validateCustomVar(env({ envName: "PROTON_LOG" }), new Set(["PROTON_LOG"]))).toBe("duplicate");
  });
  it("rejects an arg flag already taken", () => {
    expect(validateCustomVar(arg({ arg: "-novid" }), new Set(["-novid"]))).toBe("duplicate");
  });
  it("accepts a token that isn't taken", () => {
    expect(validateCustomVar(env({ envName: "MY_VAR" }), new Set(["PROTON_LOG"]))).toBeNull();
  });
  it("field errors win over duplicate", () => {
    expect(validateCustomVar(env({ envName: "" }), new Set([""]))).toBe("envName");
  });
});

describe("validateCustomVar rejects unescapable values (would corrupt the command)", () => {
  it("rejects a space in an env value", () => {
    expect(validateCustomVar(env({ envValue: "hello world" }))).toBe("unsafe");
  });
  it("rejects quotes / shell metacharacters in an env value", () => {
    expect(validateCustomVar(env({ envValue: 'a"b' }))).toBe("unsafe");
    expect(validateCustomVar(env({ envValue: "a;b" }))).toBe("unsafe");
  });
  it("rejects a multi-token arg", () => {
    expect(validateCustomVar(arg({ arg: "--foo bar" }))).toBe("unsafe");
  });
  it("still accepts ordinary values (commas, dots, equals-free)", () => {
    expect(validateCustomVar(env({ envValue: "dxgi=n,b" }))).toBeNull();
    expect(validateCustomVar(env({ envValue: "es_ES.UTF-8" }))).toBeNull();
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

  it("carries a retired definition into the pill", () => {
    expect(customVarToPill(arg({ retired: true })).retired).toBe(true);
  });
});

describe("retired custom vars", () => {
  it("shows a retired pill only while its token is active", () => {
    const pill = customVarToPill(arg({ retired: true }));
    expect(customPillVisible(pill, undefined)).toBe(false);
    expect(customPillVisible(pill, true)).toBe(true);
  });

  it("drops persisted definitions that collide with base or earlier custom tokens", () => {
    const vars = [
      env({ id: "base", envName: "PROTON_LOG" }),
      arg({ id: "first", arg: "-custom" }),
      arg({ id: "second", arg: "-custom" }),
    ];
    expect(sanitizeCustomVars(vars, new Set(["PROTON_LOG"])).map((v) => v.id)).toEqual(["first"]);
  });

  it("retires a deleted definition instead of forgetting its token", () => {
    expect(retireCustomVar([arg({ id: "old" })], "old")).toEqual([arg({ id: "old", retired: true })]);
  });

  it("keeps the old token retired when an edit changes ownership", () => {
    const before = [arg({ id: "same", arg: "-old" })];
    const draft = arg({ id: "same", arg: "-new" });
    expect(saveCustomDraft(before, draft, () => "retired-id")).toEqual([
      arg({ id: "retired-id", arg: "-old", retired: true }),
      draft,
    ]);
  });

  it("replaces in place when an edit keeps the same token", () => {
    const before = [arg({ id: "same", name: "Before" })];
    const draft = arg({ id: "same", name: "After" });
    expect(saveCustomDraft(before, draft, () => "unused")).toEqual([draft]);
  });

  it("reactivates a retired token instead of creating an unpersistable duplicate", () => {
    const retired = arg({ id: "retired", name: "Old", arg: "-same", retired: true });
    const draft = arg({ id: "new", name: "New", arg: "-same" });
    expect(saveCustomDraft([retired], draft, () => "unused")).toEqual([
      arg({ id: "retired", name: "New", arg: "-same" }),
    ]);
  });

  it("reactivates a retired token when an existing variable is edited to use it", () => {
    const retired = arg({ id: "retired", name: "Old", arg: "-same", retired: true });
    const active = arg({ id: "active", name: "Active", arg: "-other" });
    const draft = arg({ id: "active", name: "Reused", arg: "-same" });
    expect(saveCustomDraft([retired, active], draft, () => "unused")).toEqual([
      arg({ id: "retired", name: "Reused", arg: "-same" }),
      arg({ id: "active", name: "Active", arg: "-other", retired: true }),
    ]);
  });
});

describe("pillVisible exempts custom vars from PROTON_ gating", () => {
  it("a custom PROTON_ env shows even if the build doesn't list the var", () => {
    const p = customVarToPill(env({ id: "z", envName: "PROTON_WHATEVER", envValue: "1" }));
    expect(pillVisible(p, [], "rdna3")).toBe(true);
  });
});
