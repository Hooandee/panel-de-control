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
