import { describe, it, expect } from "vitest";
import { protonFamily } from "./proton";

describe("protonFamily", () => {
  it("maps real compat-tool ids to families", () => {
    expect(protonFamily("GE-Proton10-21")).toBe("ge");
    expect(protonFamily("Proton-GE Latest")).toBe("ge");
    expect(protonFamily("proton_experimental")).toBe("experimental");
    expect(protonFamily("proton_10")).toBe("stable");
    expect(protonFamily("proton_11")).toBe("stable");
  });

  it("detects CachyOS / EM", () => {
    expect(protonFamily("proton-cachyos")).toBe("cachyos");
    expect(protonFamily("proton-em-10")).toBe("cachyos");
  });

  it("empty / null → unknown", () => {
    expect(protonFamily("")).toBe("unknown");
    expect(protonFamily(null)).toBe("unknown");
    expect(protonFamily(undefined)).toBe("unknown");
  });
});
