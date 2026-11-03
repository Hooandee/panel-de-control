import { describe, expect, it } from "vitest";
import { applyLaunch, easyChoice, easyModeOf, renderHeight, revertLaunch, withEnv, withOverride, withoutOverride } from "./model";

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
