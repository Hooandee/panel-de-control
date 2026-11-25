import { describe, expect, it } from "vitest";

import cases from "../../../shared/contracts/ambient/fixtures/arbiter-cases.json";
import { arbitrate, conflictKey, type ArbiterInput } from "./arbiter";

describe("arbiter contract", () => {
  for (const c of cases) {
    it(c.name, () => {
      expect(arbitrate(c.input as ArbiterInput)).toEqual(c.expect);
    });
  }

  it("conflict key is stable per competitor", () => {
    expect(conflictKey({ kind: "theme", id: "hooandee-gallery", name: "Gallery" })).toBe("theme:hooandee-gallery");
    expect(conflictKey(null)).toBeNull();
  });
});


describe("saved painter choices", () => {
  const input = (claims: Record<string, "panel" | "other">): ArbiterInput => ({
    themeClaims: [], thirdParty: {confidence:"low",id:"css:ScrollArea",candidates:["css:ScrollArea"]},
    audioLoader:false, claims, previous:null,
  });
  it("keeps an explicit other choice when the matching theme background is ambiguous", () => {
    expect(arbitrate(input({"css:ScrollArea":"other"}))).toMatchObject({background:"other",conflict:null});
  });
  it("does not infer ownership from an ambiguous background without a matching saved choice", () => {
    expect(arbitrate(input({}))).toMatchObject({background:"panel",conflict:null});
    expect(arbitrate(input({"css:BackgroundGlass":"other"}))).toMatchObject({background:"panel",conflict:null});
    expect(arbitrate(input({"css:ScrollArea":"panel"}))).toMatchObject({background:"panel",conflict:null});
  });
});
