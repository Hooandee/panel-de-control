import { describe, it, expect } from "vitest";
import { sdtdpActive, tdpConflict, monitorOnly } from "./conflict";

describe("sdtdpActive", () => {
  it("true if installed and not disabled", () => {
    expect(sdtdpActive(["SimpleDeckyTDP", "Colores"], [])).toBe(true);
  });
  it("false if disabled", () => {
    expect(sdtdpActive(["SimpleDeckyTDP"], ["SimpleDeckyTDP"])).toBe(false);
  });
  it("false if not installed", () => {
    expect(sdtdpActive(["Colores"], [])).toBe(false);
  });
});

describe("tdpConflict", () => {
  const base = { sdtdp: false, hhdManaging: false, weControl: true, tdpSupported: true };
  it("no rivals -> false", () => {
    expect(tdpConflict(base).conflict).toBe(false);
  });
  it("SDTDP active and we control -> true", () => {
    expect(tdpConflict({ ...base, sdtdp: true }).conflict).toBe(true);
  });
  it("HHD managing and we control -> true", () => {
    expect(tdpConflict({ ...base, hhdManaging: true }).conflict).toBe(true);
  });
  it("we don't control (toggle off) -> false", () => {
    expect(tdpConflict({ ...base, sdtdp: true, weControl: false }).conflict).toBe(false);
  });
  it("no hardware support -> false", () => {
    expect(tdpConflict({ ...base, hhdManaging: true, tdpSupported: false }).conflict).toBe(false);
  });
  it("reports which rivals are active", () => {
    const r = tdpConflict({ ...base, sdtdp: true, hhdManaging: false });
    expect(r.rivals).toEqual({ sdtdp: true, hhd: false });
  });
});

describe("monitorOnly", () => {
  it("true without hardware support", () => {
    expect(monitorOnly(false, true)).toBe(true);
  });
  it("true when control is off", () => {
    expect(monitorOnly(true, false)).toBe(true);
  });
  it("false when supported and controlling", () => {
    expect(monitorOnly(true, true)).toBe(false);
  });
});
