interface Overview {
  appid?: number;
  app_type?: number;
  local_per_client_data?: { installed?: boolean };
}

const APP_TYPE_GAME = 1;
const MAX_GAMES = 60;

/** Installed Steam games whose hero art Steam already caches locally (no network, no fan-art). */
export function installedGameAppIds(): number[] {
  try {
    const store = (globalThis as unknown as { collectionStore?: { allAppsCollection?: { allApps?: Overview[] } } }).collectionStore;
    const apps = store?.allAppsCollection?.allApps ?? [];
    return apps
      .filter((app) => typeof app.appid === "number" && app.app_type === APP_TYPE_GAME && app.local_per_client_data?.installed === true)
      .map((app) => app.appid as number)
      .slice(0, MAX_GAMES);
  } catch {
    return [];
  }
}

export function libraryHeroUrl(appid: number | string): string {
  return `https://steamloopback.host/assets/${appid}/library_hero.jpg`;
}

const LOOPBACK = "https://steamloopback.host";
const HASHED_HERO = /\/apps\/(\d+)\/([0-9a-f]{40})\/library_hero\.jpg/;

function loopbackArt(path: unknown): string | null {
  if (typeof path !== "string") return null;
  try {
    const url = new URL(path, LOOPBACK);
    return url.origin === LOOPBACK && /^\/(?:assets|customimages)\//.test(url.pathname) ? url.href : null;
  } catch { return null; }
}

export type HeroSource = "custom" | "hashed" | "plain";

/**
 * The hero Steam itself shows for a game. Custom art wins; store games whose art lives under a content
 * hash are not served at the plain `library_hero.jpg` path (404); shortcuts only have custom art.
 */
export function gameHero(appid: number | string): { url: string; source: HeroSource } {
  try {
    const id = Number(appid);
    const g = globalThis as unknown as {
      appStore?: { GetAppOverviewByAppID?(id: number): unknown; GetCustomHeroImageURLs?(overview: unknown): unknown };
      appDetailsStore?: { GetHeroImagesForAppId?(id: number): { rgHeroImages?: unknown } | undefined };
    };
    const overview = g.appStore?.GetAppOverviewByAppID?.(id);
    const custom = overview ? g.appStore?.GetCustomHeroImageURLs?.(overview) : null;
    if (Array.isArray(custom)) for (const entry of custom) { const url = loopbackArt(entry); if (url) return { url, source: "custom" }; }
    const heroes = g.appDetailsStore?.GetHeroImagesForAppId?.(id)?.rgHeroImages;
    if (Array.isArray(heroes)) {
      for (const entry of heroes) {
        const hashed = typeof entry === "string" ? HASHED_HERO.exec(entry) : null;
        if (hashed && hashed[1] === String(id)) return { url: `${LOOPBACK}/assets/${id}/${hashed[2]}/library_hero.jpg`, source: "hashed" };
      }
    }
  } catch { /* Steam versions can omit these stores; the plain path still serves older art. */ }
  return { url: libraryHeroUrl(appid), source: "plain" };
}

export const gameHeroUrl = (appid: number | string): string => gameHero(appid).url;

const APP_ART = /\/(?:assets|customimages)\/(\d+)(?:[_/.p])/;

/** The game a piece of Steam art belongs to (store assets, or a non-Steam shortcut's custom art). */
export function selectedAppIdFromHero(src: string | null | undefined): string | null {
  const match = src ? APP_ART.exec(src) : null;
  return match ? match[1] : null;
}

/** Non-Steam shortcuts get ids from the top half of the 32-bit range; the store knows nothing about them. */
export function isStoreApp(appid: string): boolean {
  const id = Number(appid);
  return Number.isInteger(id) && id > 0 && id < 2 ** 31;
}

/**
 * The carousel's selected game. The focused tile is the truth: while Steam cross-fades its blurred
 * hero the previous game's image is still in the page, and a game without art has none at all.
 */
export function selectedAppIdIn(container: Element | null): string | null {
  if (!container) return null;
  const focused = container.querySelector(".gpfocus");
  if (focused) {
    for (const img of Array.from(focused.querySelectorAll("img"))) {
      const appid = selectedAppIdFromHero(img.getAttribute("src"));
      if (appid) return appid;
    }
    return null;
  }
  const view = container.ownerDocument.defaultView;
  const heroes = Array.from(container.querySelectorAll<HTMLImageElement>('img[src*="hero_blur"]'));
  const shown = heroes.filter((img) => {
    const opacity = view?.getComputedStyle(img).opacity;
    return !opacity || Number(opacity) > 0;
  }).pop();
  return selectedAppIdFromHero(shown?.getAttribute("src"));
}

/** The games beside the focused tile, nearest first, so their media can be looked up ahead of a move. */
export function neighborAppIdsIn(container: Element | null): string[] {
  const tile = container?.querySelector(".gpfocus")?.closest('[role="listitem"]');
  if (!tile) return [];
  const appidOf = (item: Element | null) => {
    for (const img of Array.from(item?.querySelectorAll("img") ?? [])) {
      const appid = selectedAppIdFromHero(img.getAttribute("src"));
      if (appid) return appid;
    }
    return null;
  };
  const ids = [appidOf(tile.nextElementSibling), appidOf(tile.previousElementSibling)];
  return ids.filter((appid): appid is string => appid !== null);
}
