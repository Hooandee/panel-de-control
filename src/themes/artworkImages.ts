import { steamArtworkUrl, type GameArtwork } from "./artwork";
export interface ArtworkImage { source: Exclude<GameArtwork["source"], "auto"> | "logo"; url: string; }
export function artworkImages(appId: number): ArtworkImage[] {
  const result: ArtworkImage[] = [];
  const store = (window as unknown as { appStore?: Record<string, any> }).appStore;
  let overview: Record<string, any> | undefined;
  try { overview = store?.GetAppOverviewByAppID?.(appId); } catch { return result; }
  if (overview?.appid !== appId) return result;
  const add = (source: ArtworkImage["source"], input: unknown) => {
    const url = steamArtworkUrl(input);
    if (url && !result.some((x) => x.url === url)) result.push({ source, url });
  };
  for (const [source, method, field] of [
    ["capsule", "GetCustomVerticalCapsuleURLs", "library_capsule_filename"],
    ["hero", "GetCustomHeroImageURLs", "library_hero_filename"],
    ["header", "GetCustomLandcapeImageURLs", "header_filename"],
    ["logo", "GetCustomLogoImageURLs", "library_logo_filename"],
  ] as const) {
    try {
      const custom = store?.[method]?.(overview);
      if (Array.isArray(custom)) for (const url of custom) add(source, url);
      const filename = overview[field];
      if (typeof filename === "string" && /^(?:[0-9a-f]+\/)?[\w.-]+\.(?:jpe?g|png|webp)$/i.test(filename)) {
        const version = overview.local_cache_version;
        add(source, `/assets/${appId}/${filename}${version == null ? "" : `?c=${encodeURIComponent(version)}`}`);
      }
    } catch { /* Steam versions can omit individual artwork accessors. */ }
  }
  const details = (window as unknown as { appDetailsStore?: Record<string, any> }).appDetailsStore;
  for (const [source, read] of [
    ["hero", () => details?.GetHeroImagesForAppId?.(appId)?.rgHeroImages],
    ["logo", () => details?.GetLogoImagesForAppId?.(appId)?.rgLogoImages],
    ["capsule", () => store?.GetCachedVerticalCapsuleURL?.(overview)],
  ] as const) {
    try {
      const urls = read();
      if (Array.isArray(urls)) for (const url of urls) add(source, url);
      else add(source, urls);
    } catch { /* Steam details can be unavailable until the game is opened. */ }
  }
  return result;
}

export function previewArtworkImage(draft: GameArtwork, images: ArtworkImage[], failed: string[]): string | undefined {
  const available = images.filter((image) => !failed.includes(image.url));
  if (draft.image && !failed.includes(draft.image)) return draft.image;
  const candidates = available.filter((image) => image.source !== "logo");
  const fallback = candidates.find((image) => image.source === "capsule")?.url
    ?? candidates.find((image) => image.source === "header")?.url;
  if (draft.source !== "auto") return candidates.find((image) => image.source === draft.source)?.url ?? fallback;
  if (!draft.showLogo || available.some((image) => image.source === "logo")) {
    const hero = candidates.find((image) => image.source === "hero");
    if (hero) return hero.url;
  }
  return fallback;
}

export function artworkSourceLabel(source: Exclude<GameArtwork["source"], "auto">, spanish: boolean): string {
  const labels = spanish
    ? { hero: "Fondo", capsule: "Portada vertical", header: "Cabecera" }
    : { hero: "Background", capsule: "Vertical cover", header: "Header" };
  return labels[source];
}

export function artworkGameTitle(appId: number, fallback?: string): string {
  try {
    const store = (window as unknown as { appStore?: { GetAppOverviewByAppID?(id: number): { appid?: number; display_name?: string } } }).appStore;
    const overview = store?.GetAppOverviewByAppID?.(appId);
    if (overview?.appid === appId && typeof overview.display_name === "string" && overview.display_name.trim()) return overview.display_name;
  } catch { /* Steam may replace its app store while the modal is open. */ }
  return fallback || String(appId);
}
