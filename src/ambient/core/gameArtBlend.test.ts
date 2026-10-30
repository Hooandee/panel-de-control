import { describe, expect, it } from "vitest";

import { chooseBackground } from "./gameArtBlend";

describe("game art blend", () => {
  it("per-game background wins in every mode", () => {
    for (const mode of ["mine", "blend", "game"] as const) {
      expect(chooseBackground(mode, "local:a", "730", { "730": "local:cs" })).toEqual({ mediaRef: "local:cs", nativeArt: "hide" });
    }
  });

  it("mine hides Steam's game art and blend dims it", () => {
    expect(chooseBackground("mine", "local:a", "730", {})).toEqual({ mediaRef: "local:a", nativeArt: "hide" });
    expect(chooseBackground("blend", "local:a", "730", {})).toEqual({ mediaRef: "local:a", nativeArt: "blend" });
  });

  it("game mode and empty rotation keep Steam native", () => {
    expect(chooseBackground("game", "local:a", null, {})).toEqual({ mediaRef: null, nativeArt: "show" });
    expect(chooseBackground("mine", null, null, {}).nativeArt).toBe("show");
  });
});
