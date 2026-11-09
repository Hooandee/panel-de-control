import { describe, expect, it } from "vitest";
import { configuredLaunchTools } from "./launchTools";

describe("configured launch tools", () => {
  it("identifies combined generators without reading unrelated values", () => {
    expect(configuredLaunchTools('TOKEN=secret LSFGVK_PROFILE=custom ~/.local/bin/mako-run %command% -dx11')).toEqual(["Mako", "Lossless Scaling"]);
  });
  it("does not claim activity or match arguments and lookalike programs", () => {
    expect(configuredLaunchTools('WINE_FULLSCREEN_FSR=0 /tmp/not-mako-run %command% mako-run')).toEqual([]);
  });
  it("accepts quoted launchers and preserves malformed commands as unknown", () => {
    expect(configuredLaunchTools('"/some path/mako-launch" %command%')).toEqual(["Mako"]);
    expect(configuredLaunchTools('mako-run %command% && echo x')).toEqual([]);
  });
});
