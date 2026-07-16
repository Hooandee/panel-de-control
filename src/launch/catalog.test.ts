import { describe, it, expect } from "vitest";
import { parse } from "./compose";
import {
  CATALOG,
  detectSelections,
  buildLaunchOptions,
  isPillAvailable,
  LaunchTools,
} from "./catalog";

const TOOLS: LaunchTools = {
  lsfg: true, mangohud: true, gamemode: true, gamescope: true,
  distro: "bazzite", locale_reliable: true,
};

describe("detectSelections", () => {
  it("lights up wrapper / env-value / arg pills from a string", () => {
    const sel = detectSelections(parse("DXVK_FRAME_RATE=60 mangohud ~/lsfg %command% -novid"));
    expect(sel.mangohud).toBe(true);
    expect(sel.lsfg).toBe(true);
    expect(sel.fpsLimit).toBe("60");
    expect(sel.noVideo).toBe(true);
    expect(sel.gamemode).toBeUndefined();
  });

  it("captures an fps value outside our chip set (so it's preserved)", () => {
    const sel = detectSelections(parse("DXVK_FRAME_RATE=45 %command%"));
    expect(sel.fpsLimit).toBe("45");
  });

  it("detects the chosen renderer flag", () => {
    expect(detectSelections(parse("%command% -dx11")).renderer).toBe("-dx11");
  });
});

describe("buildLaunchOptions", () => {
  it("adds a wrapper to a bare game, introducing %command%", () => {
    const out = buildLaunchOptions(parse(""), { mangohud: true });
    expect(out).toBe("mangohud %command%");
  });

  it("orders wrappers canonically (gamemode → mangohud → lsfg)", () => {
    const out = buildLaunchOptions(parse(""), { lsfg: true, mangohud: true, gamemode: true });
    expect(out).toBe("gamemoderun mangohud ~/lsfg %command%");
  });

  it("langEs sets LANG to Spanish", () => {
    expect(buildLaunchOptions(parse(""), { langEs: true })).toBe("LANG=es_ES.UTF-8 %command%");
  });

  it("does NOT clobber a user's own LANG value, and is not detected as active", () => {
    const base = parse("LANG=fr_FR.UTF-8 %command%");
    expect(detectSelections(base).langEs).toBeUndefined();
    // Untouched selections → the user's French locale survives, editor is not dirty.
    expect(buildLaunchOptions(base, detectSelections(base))).toBe("LANG=fr_FR.UTF-8 %command%");
  });

  it("enabling langEs over a user's LANG replaces it (no duplicate)", () => {
    const base = parse("LANG=en_US.UTF-8 %command%");
    const out = buildLaunchOptions(base, { langEs: true });
    expect(out).toBe("LANG=es_ES.UTF-8 %command%");
  });

  it("preserves a known wrapper's inline argument (mangohud --dlsym)", () => {
    const base = parse("mangohud --dlsym %command%");
    // mangohud stays active; the string must round-trip without orphaning --dlsym.
    expect(buildLaunchOptions(base, detectSelections(base))).toBe("mangohud --dlsym %command%");
  });

  it("turning a pill off removes only its tokens", () => {
    const base = parse("DXVK_FRAME_RATE=60 mangohud %command% -novid");
    const sel = detectSelections(base);
    delete sel.mangohud; // toggle MangoHud off
    const out = buildLaunchOptions(base, sel);
    expect(out).toBe("DXVK_FRAME_RATE=60 %command% -novid");
  });

  it("round-trips: detect then rebuild is stable", () => {
    const base = parse("DXVK_FRAME_RATE=60 gamemoderun mangohud %command% -novid");
    expect(buildLaunchOptions(base, detectSelections(base))).toBe(
      "DXVK_FRAME_RATE=60 gamemoderun mangohud %command% -novid",
    );
  });

  it("preserves EmuDeck/SRM content while adding our tokens", () => {
    const base = parse("SRM_LAUNCH=1 %command%");
    const out = buildLaunchOptions(base, { fpsLimit: "60", mangohud: true, noVideo: true });
    // SRM env preserved; ours inserted in the right zones.
    expect(out).toBe("SRM_LAUNCH=1 DXVK_FRAME_RATE=60 mangohud %command% -novid");
  });

  it("keeps a pre-existing unknown wrapper outermost", () => {
    const base = parse("scopebuddy -- %command%");
    const out = buildLaunchOptions(base, { mangohud: true });
    expect(out).toBe("scopebuddy -- mangohud %command%");
  });

  it("does not mutate a malformed (multi-%command%) string", () => {
    const base = parse("%command% %command%");
    expect(buildLaunchOptions(base, { mangohud: true })).toBe("%command% %command%");
  });

  it("renderer is single-choice: switching replaces the flag", () => {
    let base = parse("%command% -vulkan");
    let sel = detectSelections(base);
    expect(sel.renderer).toBe("-vulkan");
    sel.renderer = "-dx12";
    const out = buildLaunchOptions(base, sel);
    expect(out).toBe("%command% -dx12");
  });
});

describe("isPillAvailable", () => {
  it("gates on the required tool", () => {
    const lsfg = CATALOG.find((p) => p.id === "lsfg")!;
    expect(isPillAvailable(lsfg, TOOLS)).toBe(true);
    expect(isPillAvailable(lsfg, { ...TOOLS, lsfg: false })).toBe(false);
    expect(isPillAvailable(lsfg, null)).toBe(false);
  });

  it("pills without a tool requirement are always available", () => {
    const novid = CATALOG.find((p) => p.id === "noVideo")!;
    expect(isPillAvailable(novid, null)).toBe(true);
  });
});
