import { describe, it, expect } from "vitest";
import {
  REPORT_CATEGORIES,
  canSubmit,
  displayReportContext,
  toggleCategory,
} from "./logic";

describe("toggleCategory", () => {
  it("adds when absent", () => {
    expect(toggleCategory([], "tdp")).toEqual(["tdp"]);
  });
  it("removes when present", () => {
    expect(toggleCategory(["tdp", "fans"], "tdp")).toEqual(["fans"]);
  });
  it("does not mutate the input", () => {
    const sel: ("tdp")[] = ["tdp"];
    toggleCategory(sel, "tdp");
    expect(sel).toEqual(["tdp"]);
  });
});

describe("canSubmit", () => {
  it("false without a description", () => {
    expect(canSubmit([], "")).toBe(false);
    expect(canSubmit([], "   ")).toBe(false);
  });
  it("false with categories but no description", () => {
    expect(canSubmit(["fans", "display"], "")).toBe(false);
  });
  it("true once there is a description", () => {
    expect(canSubmit([], "algo falla")).toBe(true);
    expect(canSubmit(["fans"], "los ventiladores no giran")).toBe(true);
  });
});

describe("REPORT_CATEGORIES", () => {
  it("includes the expected ids", () => {
    expect(REPORT_CATEGORIES).toContain("tdp");
    expect(REPORT_CATEGORIES).toContain("audio");
    expect(REPORT_CATEGORIES).toContain("other");
  });
});

describe("displayReportContext", () => {
  it("reports the brightness methods available to a display report", () => {
    const display = {
      RegisterForBrightnessChanges() {},
      SetBrightness() {},
    };

    expect(displayReportContext(["display"], display)).toEqual({
      display: {
        brightness: {
          subscribe_available: true,
          set_available: true,
        },
      },
    });
  });

  it("reports missing Steam brightness methods without claiming support", () => {
    expect(displayReportContext(["system"], {})).toEqual({
      display: {
        brightness: {
          subscribe_available: false,
          set_available: false,
        },
      },
    });
  });

  it("does not collect display context for unrelated reports", () => {
    expect(displayReportContext(["fans"], {})).toEqual({});
  });
});
