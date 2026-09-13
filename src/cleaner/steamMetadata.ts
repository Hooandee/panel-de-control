import type { CleanerMetadata } from "./model";

interface Overview { appid?: number; display_name?: string }
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
