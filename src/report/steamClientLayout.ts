/**
 * Steam client settings that change Big Picture's layout, for the report bundle.
 *
 * A Home theme broke for many users because Settings → Home → «Fondo ampliado»
 * (`library_home_big_art`) lays the native Home out horizontally, and no bundle recorded it.
 * Only a fixed allowlist is read and only booleans / finite numbers (enum ids) leave this
 * function: anything else becomes `null`, so free text can never reach the report.
 */
export const STEAM_LAYOUT_SETTINGS = [
  "library_home_big_art",
  "library_display_size",
  "library_low_perf_mode",
  "library_low_bandwidth_mode",
  "library_disable_community_content",
  "show_store_content_on_home",
] as const;

export type SteamLayoutSetting = (typeof STEAM_LAYOUT_SETTINGS)[number];

export interface SteamClientLayoutReport {
  status: "captured" | "unavailable";
  settings: Partial<Record<SteamLayoutSetting, boolean | number | null>>;
}

interface SettingsStoreView {
  m_ClientSettings?: Record<string, unknown>;
  GetClientSetting?: (name: string) => unknown;
}

function scalar(value: unknown): boolean | number | null {
  if (typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

export function steamClientLayoutReport(
  source: unknown = typeof window === "undefined" ? undefined : window,
): SteamClientLayoutReport {
  try {
    const store = (source as { settingsStore?: SettingsStoreView } | undefined)?.settingsStore;
    const settings = store?.m_ClientSettings;
    const getter = typeof store?.GetClientSetting === "function" ? store.GetClientSetting.bind(store) : null;
    if ((!settings || typeof settings !== "object") && !getter) {
      return { status: "unavailable", settings: {} };
    }
    const result: SteamClientLayoutReport["settings"] = {};
    for (const key of STEAM_LAYOUT_SETTINGS) {
      let value: unknown = settings && typeof settings === "object" ? settings[key] : undefined;
      if (value === undefined && getter) {
        try {
          const pair = getter(key);
          value = Array.isArray(pair) ? pair[0] : undefined;
        } catch {
          value = undefined;
        }
      }
      result[key] = scalar(value);
    }
    return { status: "captured", settings: result };
  } catch {
    return { status: "unavailable", settings: {} };
  }
}
