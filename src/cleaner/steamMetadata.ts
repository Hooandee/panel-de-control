import type { CleanerMetadata } from "./model";

interface Overview {
  appid?: number;
  display_name?: string;
  app_type?: number;
  local_per_client_data?: { installed?: boolean };
}
interface SteamVisualWindow {
  collectionStore?: { allAppsCollection?: { allApps?: Overview[] } };
  appStore?: {
    GetCustomVerticalCapsuleURLs?: (overview: Overview) => unknown;
    GetVerticalCapsuleURLForApp?: (overview: Overview) => unknown;
  };
}

export function readCleanerMetadata(): Map<string, CleanerMetadata> {
  const result = new Map<string, CleanerMetadata>();
  if (typeof window === "undefined") return result;
  try {
    const steam = window as unknown as SteamVisualWindow;
    const overviews = steam.collectionStore?.allAppsCollection?.allApps;
    if (!Array.isArray(overviews)) return result;
    for (const overview of overviews) {
      if (!overview || !Number.isSafeInteger(overview.appid) || typeof overview.display_name !== "string") continue;
      const coverUrls: string[] = [];
      try {
        const custom = steam.appStore?.GetCustomVerticalCapsuleURLs?.(overview);
        const capsule = steam.appStore?.GetVerticalCapsuleURLForApp?.(overview);
        for (const url of [...(Array.isArray(custom) ? custom : []), capsule]) {
          if (typeof url === "string" && url) coverUrls.push(url.startsWith("/") ? `https://steamloopback.host${url}` : url);
        }
      } catch { /* Steam artwork is optional and never authorizes deletion. */ }
      result.set(String(overview.appid), { name: overview.display_name, coverUrls });
    }
  } catch { /* Steam stores can be absent while the QAM is mounting. */ }
  return result;
}

export function readInstalledCleanerMetadata(metadata = readCleanerMetadata()): Array<CleanerMetadata & { appid: string }> {
  if (typeof window === "undefined") return [];
  try {
    const overviews = (window as unknown as SteamVisualWindow).collectionStore?.allAppsCollection?.allApps;
    if (!Array.isArray(overviews)) return [];
    return overviews.flatMap((overview) => {
      if (!Number.isSafeInteger(overview.appid) || overview.app_type === 4 || overview.local_per_client_data?.installed !== true) return [];
      const visual = metadata.get(String(overview.appid));
      return visual ? [{ appid: String(overview.appid), ...visual }] : [];
    });
  } catch {
    return [];
  }
}

export function readInstalledProtonMetadata(): Array<{ appid: string; name: string }> {
  if (typeof window === "undefined") return [];
  try {
    const overviews = (window as unknown as SteamVisualWindow).collectionStore?.allAppsCollection?.allApps;
    if (!Array.isArray(overviews)) return [];
    return overviews.flatMap((overview) => {
      const name = typeof overview.display_name === "string" ? overview.display_name.trim() : "";
      const isProton = name.toLocaleLowerCase().includes("proton");
      const isRuntime = name.toLocaleLowerCase().includes("steam linux runtime");
      if (!Number.isSafeInteger(overview.appid) || overview.app_type !== 4 || overview.local_per_client_data?.installed !== true || (!isProton && !isRuntime)) return [];
      return [{ appid: String(overview.appid), name }];
    });
  } catch {
    return [];
  }
}
