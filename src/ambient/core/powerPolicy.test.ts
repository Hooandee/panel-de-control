import { describe, expect, it } from "vitest";

import cases from "../../../shared/contracts/ambient/fixtures/power-cases.json";
import { motionFor, type PowerInput } from "./powerPolicy";

describe("power policy contract", () => {
  for (const c of cases) {
    it(c.name, () => {
      expect(motionFor(c.input as PowerInput)).toBe(c.expect);
    });
  }
});
