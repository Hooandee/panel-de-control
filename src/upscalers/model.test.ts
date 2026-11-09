import { describe, expect, it } from "vitest";
import { alreadyThere, applyLaunch, buildBlocker, downloadPace, launchAfterJob, buildLabel, defaultChoice, fgOffer, lastOutputHeight, renderHeight, restoredChoice, revertLaunch, withEnv, withOverride, withoutOverride } from "./model";

describe("upscaler model", () => {
  it("keeps the last measured output height after an unverifiable DLL result", () => {
    const history = [
      { facts: { resolution: { render: [640, 360], output: [1280, 720] } } },
      { facts: { present: false, unverifiable: true } },
    ];
    expect(lastOutputHeight(history)).toBe(720);
    expect(renderHeight(lastOutputHeight(history) ?? 1280, "quality")).toBe(480);
    expect(lastOutputHeight([...history, { facts: { resolution: { render: [0, 0], output: [0, 0] } } }])).toBe(720);
    expect(lastOutputHeight([])).toBeUndefined();
  });

  it("adds the proxy override without touching other launch options", () => {
    expect(withOverride("", "dxgi=n,b")).toBe('WINEDLLOVERRIDES="dxgi=n,b" %command%');
    expect(withOverride('WINEDLLOVERRIDES="winmm=n,b" mangohud %command% -dx12', "dxgi=n,b"))
      .toBe('WINEDLLOVERRIDES="winmm,dxgi=n,b" mangohud %command% -dx12');
    expect(withOverride('WINEDLLOVERRIDES="dxgi=b" %command%', "dxgi=n,b")).toBeNull();
    expect(withOverride('WINEDLLOVERRIDES="winmm=b" %command%', "dxgi=n,b")).toBe('WINEDLLOVERRIDES="winmm=b;dxgi=n,b" %command%');
  });

  it("removes only its own override", () => {
    expect(withoutOverride('WINEDLLOVERRIDES="dxgi=n,b" %command%', "dxgi=n,b")).toBe("");
    expect(withoutOverride('WINEDLLOVERRIDES="winmm,dxgi=n,b" gamemoderun %command%', "dxgi=n,b"))
      .toBe('WINEDLLOVERRIDES="winmm=n,b" gamemoderun %command%');
  });

  it("refuses to rewrite launch options it cannot model", () => {
    expect(withOverride('sh -c "x %command%"', "dxgi=n,b")).toBeNull();
  });

  it("preserves ordered mixed DLL modes and custom wrappers through installation and removal", () => {
    const original = 'WINEDLLOVERRIDES="winmm=b;version=n,b" LSFGVK_PROFILE="my profile" ~/.local/bin/mako-launch --quality high ~/lsfg %command% -dx12';
    const applied = applyLaunch(original, ["dxgi=n,b"], ["--launcher-skip"]);
    expect(applied?.value).toContain('WINEDLLOVERRIDES="winmm=b;version,dxgi=n,b"');
    expect(revertLaunch(applied!.value, ["dxgi=n,b"], applied!.added)).toBe(original);
    expect(alreadyThere(original, ["version=n,b"], {}).overrides).toEqual(["version=n,b"]);
  });

  it("does not replace an existing DLL mode or ambiguous duplicate assignment", () => {
    expect(withOverride('WINEDLLOVERRIDES="DXGI=b;version=n,b" %command%', "dxgi=n,b")).toBeNull();
    expect(withOverride('WINEDLLOVERRIDES="dxgi=n,b" WINEDLLOVERRIDES="version=b" %command%', "dinput8=n,b")).toBeNull();
  });

  it("starts new installs at native resolution and shows each quality's real height", () => {
    expect(defaultChoice("fsr-4.1.2").quality).toBe("native");
    expect(renderHeight(800, "native")).toBe(800);
    expect(renderHeight(800, "balanced")).toBe(471);
  });

  it("applies a recipe's dlls and args and reverts only what it added", () => {
    const applied = applyLaunch("%command% -dx12", ["dxgi=n,b", "dinput8=n,b"], ["--launcher-skip", "-dx12"]);
    expect(applied).toEqual({ value: 'WINEDLLOVERRIDES="dxgi,dinput8=n,b" %command% -dx12 --launcher-skip', added: ["--launcher-skip"] });
    expect(revertLaunch(applied!.value, ["dxgi=n,b", "dinput8=n,b"], applied!.added)).toBe("%command% -dx12");
  });
});

describe("withEnv", () => {
  it("adds and removes variables without touching the rest", () => {
    const on = withEnv('WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12', { ENABLE_GAMESCOPE_WSI: "0" });
    expect(on).toContain("ENABLE_GAMESCOPE_WSI=0");
    expect(on).toContain('WINEDLLOVERRIDES="dxgi=n,b"');
    expect(on).toContain("-dx12");
    expect(withEnv(on!, { ENABLE_GAMESCOPE_WSI: null })).toBe('WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12');
  });
});

describe("HelixSR builds", () => {
  it("are named after HelixSR's own upscalers", () => {
    expect(buildLabel({ family: "helixsr", version: "FSR 4", channel: "beta" })).toBe("HLX FSR 4 Beta");
  });

  it("HLX FSR 4 needs the game's FSR 3.1", () => {
    expect(buildBlocker({ way: "fsr" }, { dlss: [] })).toBe("needsFsr31");
    expect(buildBlocker({ way: "fsr" }, { fsr31: [] })).toBeNull();
    expect(buildBlocker({ engine: "optiscaler" }, {})).toBeNull();
  });
});

describe("launchAfterJob", () => {
  it("drops what the replaced install left and adds the new one", () => {
    const next = launchAfterJob('WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12', {
      overrides: [], args: [], removed_overrides: ["dxgi=n,b"], removed_args: ["-dx12"], env: { FSR4_UPGRADE: "1" },
    }, "install");
    expect(next?.value).toBe("FSR4_UPGRADE=1 %command%");
  });

  it("takes Proton's switch out on removal", () => {
    expect(launchAfterJob("FSR4_UPGRADE=1 %command%", { overrides: [], args: [], env: { FSR4_UPGRADE: null } }, "uninstall")?.value)
      .toBe("");
  });
});

describe("Proton FSR 4", () => {
  it("needs FSR 3.1 in the game and a Proton that has the switch", () => {
    expect(buildBlocker({ engine: "proton" }, {}, "FSR4_UPGRADE")).toBe("needsFsr31");
    expect(buildBlocker({ engine: "proton" }, { fsr31: [] }, null)).toBe("needsProton");
    expect(buildBlocker({ engine: "proton" }, { fsr31: [] }, "FSR4_UPGRADE")).toBeNull();
    expect(buildLabel({ family: "proton", version: "FSR 4" })).toBe("FSR 4 (Proton)");
  });
});

describe("downloadPace", () => {
  it("gives speed and time left, and nothing to promise while stalled", () => {
    const pace = downloadPace({ done: 0, at: 0 }, { done: 2_000_000, at: 1000 }, 10_000_000);
    expect(pace).toEqual({ rate: 2_000_000, eta: 4 });
    expect(downloadPace({ done: 5, at: 0 }, { done: 5, at: 1000 }, 10).eta).toBeNull();
  });
});

describe("frame generation offer", () => {
  it("keeps an installed generator available to turn off without offering it to new installs", () => {
    const routes = { game: { input: "fsrfg" }, optiscaler: {} };
    expect(fgOffer(routes, { fsrfg: [] }, "rdna2", false, "game").options).toEqual(["game"]);
    expect(fgOffer(routes, { fsrfg: [] }, "rdna2", false, "optiscaler").options).toEqual(["optiscaler"]);
    expect(fgOffer(routes, { fsrfg: [] }, "rdna2", false, null).options).toEqual([]);
    expect(fgOffer({}, {}, "rdna2", false, "game").options).toEqual(["game"]);
    expect(fgOffer({ game: { input: "dlssg" } }, { dlssg: [] }, "rdna2", false, "game").options).toEqual(["game"]);
  });

  it("only points to the game's own generator when it already runs on this GPU", () => {
    expect(fgOffer({ game: { input: "fsrfg" }, optiscaler: {} }, { fsrfg: [] }, "rdna2", false)).toEqual({ own: "fsr", options: [] });
    expect(fgOffer({ game: { input: "xefg" } }, { xefg: [] }, "intel", true)).toEqual({ own: "xess", options: ["lsfg"] });
    expect(fgOffer({ game: { input: "dlssg" } }, { dlssg: [] }, "nvidia", false)).toEqual({ own: "dlss", options: [] });
  });

  it("offers DLSS FG through OptiScaler off NVIDIA", () => {
    expect(fgOffer({ game: { input: "dlssg" }, optiscaler: {} }, { dlssg: [] }, "rdna3", true)).toEqual({ own: null, options: ["game", "lsfg"] });
  });

  it("offers OptiScaler's own only when the game brings none", () => {
    expect(fgOffer({ optiscaler: {} }, {}, "intel", false)).toEqual({ own: null, options: ["optiscaler"] });
    expect(fgOffer({}, {}, "rdna2", false)).toEqual({ own: null, options: [] });
    expect(fgOffer({}, {}, "rdna2", true)).toEqual({ own: null, options: ["lsfg"] });
  });
});

describe("launch options the user already had", () => {
  it("are not counted as Panel's own", () => {
    expect(alreadyThere('WINEDLLOVERRIDES="dxgi=n,b" FSR4_UPGRADE=1 %command%', ["dxgi=n,b", "winmm=n,b"], { FSR4_UPGRADE: "1" }))
      .toEqual({ overrides: ["dxgi=n,b"], env: ["FSR4_UPGRADE"] });
    const next = launchAfterJob('WINEDLLOVERRIDES="dxgi=n,b" %command%', { overrides: ["dxgi=n,b"], args: [] }, "install");
    expect(next?.addedOverrides).toEqual([]);
  });

  it("starts from the installed build only while this GPU can still take it", () => {
    const builds = [
      { id: "xess", supported: true, available: true },
      { id: "fsr-4.1.2-beta", supported: false, available: true },
      { id: "old", supported: true, available: false },
    ] as unknown as Parameters<typeof restoredChoice>[2];
    const options = { quality: "balanced" as const, sharpness: "soft" as const };
    expect(restoredChoice("xess", options, builds, "xess")).toEqual({ build: "xess", ...options });
    expect(restoredChoice("fsr-4.1.2-beta", options, builds, "xess").build).toBe("xess");
    expect(restoredChoice("old", options, builds, "xess").build).toBe("xess");
  });
});

it("keeps previously installed routes available for user choice", () => {
  expect(fgOffer({}, { fsrfg: [] }, "rdna3", true, "optiscaler")).toEqual({ own: "fsr", options: ["optiscaler", "lsfg"] });
  expect(fgOffer({ optiscaler: {} }, {}, "rdna3", false, null).options).toEqual(["optiscaler"]);
});
