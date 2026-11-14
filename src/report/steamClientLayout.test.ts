import { describe, expect, it } from "vitest";
import { STEAM_LAYOUT_SETTINGS, steamClientLayoutReport } from "./steamClientLayout";
import { buildReportContext } from "./logic";

describe("steamClientLayoutReport", () => {
  it("records Fondo ampliado (library_home_big_art) from Steam's client settings", () => {
    const report = steamClientLayoutReport({
      settingsStore: {
        m_ClientSettings: {
          library_home_big_art: true,
          library_low_perf_mode: false,
          library_display_size: 1,
          show_store_content_on_home: "user typed text",
          steam_account_name: "private",
        },
      },
    });

    expect(STEAM_LAYOUT_SETTINGS).toContain("library_home_big_art");
    expect(report.status).toBe("captured");
    expect(report.settings.library_home_big_art).toBe(true);
    expect(report.settings.library_low_perf_mode).toBe(false);
    expect(report.settings.library_display_size).toBe(1);
    expect(report.settings.show_store_content_on_home).toBeNull();
    expect(report.settings).not.toHaveProperty("steam_account_name");
  });

  it("falls back to GetClientSetting when m_ClientSettings is missing", () => {
    const report = steamClientLayoutReport({
      settingsStore: {
        GetClientSetting: (name: string) => [name === "library_home_big_art" ? false : undefined, () => {}],
      },
    });

    expect(report.status).toBe("captured");
    expect(report.settings.library_home_big_art).toBe(false);
  });

  it("reports unavailable without a settings store and never throws", () => {
    expect(steamClientLayoutReport({})).toEqual({ status: "unavailable", settings: {} });
    const hostile = { get settingsStore(): never { throw new Error("boom"); } };
    expect(steamClientLayoutReport(hostile)).toEqual({ status: "unavailable", settings: {} });
  });

  it("is part of every report context", () => {
    const context = buildReportContext([], undefined, {}, {});
    expect(context).toHaveProperty("steam_client_layout");
  });
});
