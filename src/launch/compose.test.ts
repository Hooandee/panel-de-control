import { describe, it, expect } from "vitest";
import {
  parse,
  serialize,
  getEnv,
  setEnv,
  hasWrapper,
  addWrapper,
  removeWrapper,
  hasArg,
  addArg,
  removeArg,
} from "./compose";

describe("parse", () => {
  it("empty string → empty parsed", () => {
    const p = parse("");
    expect(p).toEqual({ envs: [], wrappers: [], suffix: [], hasCommand: false, malformed: false, raw: "" });
  });

  it("no %command% → all tokens are suffix args", () => {
    const p = parse("-novid -high");
    expect(p.hasCommand).toBe(false);
    expect(p.suffix).toEqual(["-novid", "-high"]);
    expect(p.envs).toEqual([]);
    expect(p.wrappers).toEqual([]);
  });

  it("splits env / wrapper / suffix around %command%", () => {
    const p = parse("DXVK_FRAME_RATE=60 mangohud %command% -novid");
    expect(p.hasCommand).toBe(true);
    expect(p.envs).toEqual([{ name: "DXVK_FRAME_RATE", value: "60" }]);
    expect(p.wrappers).toEqual(["mangohud"]);
    expect(p.suffix).toEqual(["-novid"]);
  });

  it("keeps quoted values intact", () => {
    const p = parse('WINEDLLOVERRIDES="dxgi=n,b" %command%');
    expect(p.envs).toEqual([{ name: "WINEDLLOVERRIDES", value: '"dxgi=n,b"' }]);
  });

  it("multiple wrappers preserved in order", () => {
    const p = parse("gamemoderun mangohud ~/lsfg %command%");
    expect(p.wrappers).toEqual(["gamemoderun", "mangohud", "~/lsfg"]);
  });

  it("flags multiple %command% as malformed", () => {
    const p = parse("%command% %command%");
    expect(p.malformed).toBe(true);
  });

  it("treats shell line breaks as malformed", () => {
    expect(parse("echo prep\n%command%").malformed).toBe(true);
    expect(parse("%command%\r--second-command").malformed).toBe(true);
  });
});

describe("serialize", () => {
  it("round-trips a full string", () => {
    const s = "DXVK_FRAME_RATE=60 mangohud %command% -novid";
    expect(serialize(parse(s))).toBe(s);
  });

  it("empty parsed → empty string (no bare %command%)", () => {
    expect(serialize(parse(""))).toBe("");
    expect(serialize({ envs: [], wrappers: [], suffix: [], hasCommand: true, malformed: false, raw: "" })).toBe("");
  });

  it("args-only stays args-only (no %command% introduced)", () => {
    expect(serialize(parse("-novid"))).toBe("-novid");
  });

  it("introduces %command% when an env is added to an args-only string", () => {
    let p = parse("-novid");
    p = setEnv(p, "DXVK_FRAME_RATE", "60");
    expect(serialize(p)).toBe("DXVK_FRAME_RATE=60 %command% -novid");
  });
});

describe("env primitives", () => {
  it("get / set / upsert / remove by name", () => {
    let p = parse("%command%");
    expect(getEnv(p, "LANG")).toBeNull();
    p = setEnv(p, "LANG", "es_ES.UTF-8");
    expect(getEnv(p, "LANG")).toBe("es_ES.UTF-8");
    p = setEnv(p, "LANG", "en_US.UTF-8"); // upsert replaces value
    expect(p.envs.filter((e) => e.name === "LANG")).toHaveLength(1);
    expect(getEnv(p, "LANG")).toBe("en_US.UTF-8");
    p = setEnv(p, "LANG", null);
    expect(getEnv(p, "LANG")).toBeNull();
  });

  it("preserves an unknown env when removing another", () => {
    let p = parse("SRM_LAUNCH=1 DXVK_FRAME_RATE=60 %command%");
    p = setEnv(p, "DXVK_FRAME_RATE", null);
    expect(getEnv(p, "SRM_LAUNCH")).toBe("1");
    expect(serialize(p)).toBe("SRM_LAUNCH=1 %command%");
  });
});

describe("wrapper primitives", () => {
  it("add is idempotent; remove targets one token", () => {
    let p = parse("~/lsfg %command%");
    expect(hasWrapper(p, "~/lsfg")).toBe(true);
    p = addWrapper(p, "~/lsfg"); // no dupe
    p = addWrapper(p, "mangohud");
    expect(p.wrappers).toEqual(["~/lsfg", "mangohud"]);
    p = removeWrapper(p, "~/lsfg");
    expect(p.wrappers).toEqual(["mangohud"]);
  });
});

describe("arg primitives", () => {
  it("add is idempotent; remove targets one flag", () => {
    let p = parse("%command% -novid");
    expect(hasArg(p, "-novid")).toBe(true);
    p = addArg(p, "-novid");
    p = addArg(p, "-high");
    expect(p.suffix).toEqual(["-novid", "-high"]);
    p = removeArg(p, "-novid");
    expect(p.suffix).toEqual(["-high"]);
  });
});

describe("EmuDeck/SRM preservation", () => {
  it("keeps a complex pre-existing string intact through a round-trip", () => {
    const s = 'SRM_LAUNCH=1 WINEDLLOVERRIDES="dxgi=n,b" gamescope -w 1280 -h 800 -- %command% -bigpicture';
    const p = parse(s);
    expect(serialize(p)).toBe(s);
  });
});
