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
 * A theme that draws its own Home hides the carousel without unmounting it, so a hidden carousel
 * selects nothing: its last hero is not what the user is looking at.
 */
export function selectedAppIdIn(container: Element | null): string | null {
  if (!container?.checkVisibility({ opacityProperty: true, visibilityProperty: true })) return null;
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
