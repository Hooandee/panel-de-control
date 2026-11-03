import { describe, expect, it } from "vitest";
import { applyLaunch, buildBlocker, downloadPace, launchAfterJob, buildLabel, easyChoice, easyModeOf, renderHeight, revertLaunch, withEnv, withOverride, withoutOverride } from "./model";

describe("upscaler model", () => {
  it("adds the proxy override without touching other launch options", () => {
    expect(withOverride("", "dxgi=n,b")).toBe('WINEDLLOVERRIDES="dxgi=n,b" %command%');
    expect(withOverride('WINEDLLOVERRIDES="winmm=n,b" mangohud %command% -dx12', "dxgi=n,b"))
      .toBe('WINEDLLOVERRIDES="winmm,dxgi=n,b" mangohud %command% -dx12');
    expect(withOverride('WINEDLLOVERRIDES="dxgi=b" %command%', "dxgi=n,b")).toBe('WINEDLLOVERRIDES="dxgi=n,b" %command%');
    expect(withOverride('WINEDLLOVERRIDES="winmm=b" %command%', "dxgi=n,b")).toBeNull();
  });

  it("removes only its own override", () => {
    expect(withoutOverride('WINEDLLOVERRIDES="dxgi=n,b" %command%', "dxgi=n,b")).toBe("");
    expect(withoutOverride('WINEDLLOVERRIDES="winmm,dxgi=n,b" gamemoderun %command%', "dxgi=n,b"))
      .toBe('WINEDLLOVERRIDES="winmm=n,b" gamemoderun %command%');
  });

  it("refuses to rewrite launch options it cannot model", () => {
    expect(withOverride('sh -c "x %command%"', "dxgi=n,b")).toBeNull();
  });

  it("maps easy presets to cards and back", () => {
    const choice = easyChoice("fps", "fsr-4.1.1-rdna2");
    expect(easyModeOf(choice, "fsr-4.1.1-rdna2")).toBe("fps");
    expect(easyModeOf({ ...choice, sharpness: "off" }, "fsr-4.1.1-rdna2")).toBeNull();
    expect(easyModeOf(choice, "xess")).toBeNull();
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
    expect(buildLabel({ family: "helixsr", version: "DLSS" })).toBe("HLX DLSS");
  });

  it("HLX FSR 4 needs the game's FSR 3.1, HLX DLSS does not", () => {
    expect(buildBlocker({ way: "fsr" }, { dlss: [] })).toBe("needsFsr31");
    expect(buildBlocker({ way: "fsr" }, { fsr31: [] })).toBeNull();
    expect(buildBlocker({ way: "scaler" }, {})).toBeNull();
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
