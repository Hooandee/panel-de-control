import { beforeEach, describe, it, expect } from "vitest";
import {
  recordSteamPerformanceDiagnostic,
  resetSteamPerformanceDiagnostics,
} from "../steam/performanceDiagnostics";
import {
  REPORT_CATEGORIES,
  buildReportContext,
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
    expect(REPORT_CATEGORIES).toContain("cpu_gpu");
    expect(REPORT_CATEGORIES).toContain("audio");
    expect(REPORT_CATEGORIES).toContain("other");
  });

  it("toggles CPU and GPU control reports", () => {
    expect(toggleCategory([], "cpu_gpu")).toEqual(["cpu_gpu"]);
  });

  it("offers performance HUD reports", () => {
    expect(REPORT_CATEGORIES).toContain("hud");
    expect(toggleCategory([], "hud")).toEqual(["hud"]);
  });

  it("offers themes as a unique category before the generic fallback", () => {
    expect(REPORT_CATEGORIES.filter((id) => id === "themes")).toEqual(["themes"]);
    expect(REPORT_CATEGORIES.indexOf("themes")).toBeLessThan(
      REPORT_CATEGORIES.indexOf("other"),
    );
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

describe("buildReportContext", () => {
  beforeEach(resetSteamPerformanceDiagnostics);

  it("marks a feature request without replacing its diagnostic context", () => {
    expect(buildReportContext(
      ["themes"],
      {},
      { runningGame: { appid: "123" }, report_kind: "bug" },
      { rendered_count: 1, rendered_unique_count: 1 },
      "feature",
    )).toEqual({
      runningGame: { appid: "123" },
      qam: { rendered_count: 1, rendered_unique_count: 1 },
      report_kind: "feature",
    });
  });

  it("includes bounded QAM diagnostics with the existing frontend context", () => {
    expect(buildReportContext(
      ["other"],
      {},
      { runningGame: { appid: "123" } },
      { rendered_count: 9, rendered_unique_count: 8 },
    )).toEqual({
      runningGame: { appid: "123" },
      qam: { rendered_count: 9, rendered_unique_count: 8 },
      report_kind: "bug",
    });
  });

  it("keeps the HUD Steam state beside the existing report context", () => {
    const steamOverlay = {
      snapshot_status: "unavailable",
      resolver: "unavailable",
      settings_available: false,
      read_available: false,
      write_available: false,
      raw_level: null,
      ui_level: null,
      master_enabled: null,
      service_state: null,
      show_over_steam: null,
      last_activation: {
        outcome: "unavailable",
        before_level: null,
        requested_level: null,
        observed_level: null,
      },
    } as const;

    expect(buildReportContext(
      ["hud"],
      {},
      {},
      { rendered_count: 1 },
      "bug",
      steamOverlay,
    )).toEqual({
      hud: { steam_overlay: steamOverlay },
      qam: { rendered_count: 1 },
      report_kind: "bug",
    });
  });

  it("includes bounded Steam performance diagnostics in the frontend context", () => {
    recordSteamPerformanceDiagnostic("profile", {
      status: "request_failed",
      running_game_id: "42",
    });

    expect(buildReportContext(["other"], {}, {}, {}, "bug")).toMatchObject({
      steam_performance: {
        schema: 1,
        current: {
          profile: {
            status: "request_failed",
            running_game_id: "42",
          },
        },
        events: [
          {
            sequence: 1,
            area: "profile",
            data: {
              status: "request_failed",
              running_game_id: "42",
            },
          },
        ],
      },
    });
  });
});
