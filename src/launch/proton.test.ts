import { describe, it, expect } from "vitest";
import { protonFamily, upscalerSupported } from "./proton";

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

describe("upscalerSupported", () => {
  it("FSR4 only on RDNA3/RDNA4", () => {
    expect(upscalerSupported("fsr4", "rdna3")).toBe(true);
    expect(upscalerSupported("fsr4", "rdna4")).toBe(true);
    expect(upscalerSupported("fsr4", "rdna2")).toBe(false);
    expect(upscalerSupported("fsr4", "rdna35")).toBe(false);
    expect(upscalerSupported("fsr4", "intel")).toBe(false);
    expect(upscalerSupported("fsr4", "unknown")).toBe(false);
  });

  it("FSR3 across AMD, not Intel", () => {
    expect(upscalerSupported("fsr3", "rdna2")).toBe(true);
    expect(upscalerSupported("fsr3", "rdna35")).toBe(true);
    expect(upscalerSupported("fsr3", "intel")).toBe(false);
  });

  it("XeSS cross-vendor", () => {
    expect(upscalerSupported("xess", "intel")).toBe(true);
    expect(upscalerSupported("xess", "rdna3")).toBe(true);
  });
});
