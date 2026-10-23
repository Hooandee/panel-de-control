import { describe, expect, it } from "vitest";
import { fsrUnavailableReason } from "./fsrAvailability";
import { CATALOG, pillVisible } from "./catalog";

describe("FSR availability explanation", () => {
  it.each(["loading", "missing", "error"] as const)("explains %s without exposing a variable", (status) => {
    expect(fsrUnavailableReason("rdna3", { status, envs: [] })).toBe(`params.fsr4.${status}`);
  });
  it("explains a detected build without support", () => {
    expect(fsrUnavailableReason("rdna4", { status: "ready", envs: [] })).toBe("params.fsr4.unsupported");
  });
  it.each(["rdna2", "rdna35", "intel", "unknown"] as const)("does not expand the GPU gate to %s", (gpu) => {
    expect(fsrUnavailableReason(gpu, { status: "missing", envs: [] })).toBeUndefined();
  });
  it.each([
    ["rdna3", "PROTON_FSR4_RDNA3_UPGRADE"],
    ["rdna4", "PROTON_FSR4_UPGRADE"],
    ["rdna3", "FSR4_UPGRADE"],
    ["rdna4", "FSR4_UPGRADE"],
  ] as const)("uses only the confirmed variant for %s %s", (gpu, env) => {
    const envs = [env, "FSR4_UPGRADE"];
    expect(fsrUnavailableReason(gpu, { status: "ready", envs })).toBeUndefined();
    expect(CATALOG.filter((p) => p.exclusiveGroup === "fsr4-upgrade" && pillVisible(p, envs, gpu))).toHaveLength(1);
  });
  it("does not accept the other GPU's custom flag", () => {
    expect(fsrUnavailableReason("rdna3", { status: "ready", envs: ["PROTON_FSR4_UPGRADE"] })).toBe("params.fsr4.unsupported");
  });
});
