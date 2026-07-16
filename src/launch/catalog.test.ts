import { describe, it, expect } from "vitest";
import { parse } from "./compose";
import {
  CATALOG,
  detectSelections,
  buildLaunchOptions,
  isPillAvailable,
  frequentPills,
  pillVisible,
  LaunchTools,
} from "./catalog";

const TOOLS: LaunchTools = {
  lsfg: true, mangohud: true, gamemode: true, gamescope: true,
  distro: "bazzite", locale_reliable: true,
};

describe("detectSelections", () => {
  it("lights up wrapper / arg pills from a string", () => {
    const sel = detectSelections(parse("mangohud ~/lsfg %command% -novid"));
    expect(sel.mangohud).toBe(true);
    expect(sel.lsfg).toBe(true);
    expect(sel.noVideo).toBe(true);
    expect(sel.gamemode).toBeUndefined();
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
    const out = buildLaunchOptions(base, { mangohud: true, noVideo: true });
    // SRM env preserved; ours inserted in the right zones.
    expect(out).toBe("SRM_LAUNCH=1 mangohud %command% -novid");
  });

  it("preserves an unknown env we no longer own (e.g. DXVK_FRAME_RATE)", () => {
    const base = parse("DXVK_FRAME_RATE=60 mangohud %command% -novid");
    const sel = detectSelections(base); // DXVK_FRAME_RATE not detected (no pill owns it)
    expect(sel.fpsLimit).toBeUndefined();
    expect(buildLaunchOptions(base, sel)).toBe("DXVK_FRAME_RATE=60 mangohud %command% -novid");
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

describe("free-text pill (WINEDLLOVERRIDES)", () => {
  it("detects and preserves the typed value", () => {
    const base = parse('WINEDLLOVERRIDES="dxgi=n,b" %command%');
    expect(detectSelections(base).winedll).toBe('"dxgi=n,b"');
    expect(buildLaunchOptions(base, detectSelections(base))).toBe('WINEDLLOVERRIDES="dxgi=n,b" %command%');
  });

  it("writes the user's value", () => {
    expect(buildLaunchOptions(parse(""), { winedll: "dxgi=n,b" })).toBe("WINEDLLOVERRIDES=dxgi=n,b %command%");
  });

  it("an empty free-text value contributes nothing", () => {
    expect(buildLaunchOptions(parse(""), { winedll: "" })).toBe("");
    expect(buildLaunchOptions(parse(""), { winedll: "   " })).toBe("");
  });
});

describe("windowMode single-choice arg", () => {
  it("switching replaces the flag", () => {
    let base = parse("%command% -windowed");
    const sel = detectSelections(base);
    expect(sel.windowMode).toBe("-windowed");
    sel.windowMode = "-fullscreen";
    expect(buildLaunchOptions(base, sel)).toBe("%command% -fullscreen");
  });
});

describe("frequentPills", () => {
  const tools: LaunchTools = { lsfg: true, mangohud: true, gamemode: true, gamescope: true, distro: "bazzite", locale_reliable: true };

  it("returns most-used available pills, most-first, capped", () => {
    const top = frequentPills({ noVideo: 5, mangohud: 9, protonLog: 1 }, tools, 2);
    expect(top.map((p) => p.id)).toEqual(["mangohud", "noVideo"]);
  });

  it("excludes pills with no usage and unavailable tools", () => {
    const top = frequentPills({ lsfg: 3, noVideo: 2 }, { ...tools, lsfg: false });
    expect(top.map((p) => p.id)).toEqual(["noVideo"]); // lsfg tool absent → dropped
  });

  it("empty usage → no frequents", () => {
    expect(frequentPills({}, tools)).toEqual([]);
  });
});

describe("pillVisible (Proton capability + GPU gating)", () => {
  const pill = (id: string) => CATALOG.find((p) => p.id === id)!;

  it("a PROTON_ env pill shows only when the build supports its var", () => {
    expect(pillVisible(pill("protonHdr"), ["PROTON_ENABLE_HDR"], "rdna3")).toBe(true);
    expect(pillVisible(pill("protonHdr"), [], "rdna3")).toBe(false);
  });

  it("non-Proton pills always show (wrappers, LANG, args)", () => {
    expect(pillVisible(pill("mangohud"), [], "unknown")).toBe(true);
    expect(pillVisible(pill("langEs"), [], "unknown")).toBe(true);
    expect(pillVisible(pill("noVideo"), [], "unknown")).toBe(true);
  });

  it("FSR4 needs its var supported AND the right GPU", () => {
    expect(pillVisible(pill("fsr4"), ["PROTON_FSR4_UPGRADE"], "rdna4")).toBe(true);
    expect(pillVisible(pill("fsr4"), ["PROTON_FSR4_UPGRADE"], "rdna3")).toBe(false); // wrong GPU
    expect(pillVisible(pill("fsr4Rdna3"), ["PROTON_FSR4_RDNA3_UPGRADE"], "rdna3")).toBe(true);
    expect(pillVisible(pill("fsr4Rdna3"), [], "rdna3")).toBe(false); // var unsupported by build
    expect(pillVisible(pill("fsr4Rdna3"), ["PROTON_FSR4_RDNA3_UPGRADE"], "rdna2")).toBe(false); // Steam Deck
  });

  it("OptiScaler shows only where its var exists (CachyOS)", () => {
    expect(pillVisible(pill("optiscaler"), ["PROTON_USE_OPTISCALER"], "rdna3")).toBe(true);
    expect(pillVisible(pill("optiscaler"), [], "rdna3")).toBe(false);
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
