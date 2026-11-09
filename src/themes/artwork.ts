export interface GameArtwork {
  source: "auto" | "capsule" | "header" | "hero";
  image: string | null;
  positionX: number;
  positionY: number;
  showLogo: boolean;
  showTitle: boolean;
  /** Percent, 50-200; absent means 100. */
  logoScale?: number;
  /** Logo position in percent, 0-100; absent means 50 (centred). */
  logoPositionX?: number;
  logoPositionY?: number;
}
/**
 * Where the logo sits on a cover. Its box (78 % x 36 %, centred at 50/50) slides to the cover's edges and the
 * logo moves inside it the same way, so 0 and 100 put it against the edge. Themes reproduce the same placement.
 */
export function logoPlacement(art: Pick<GameArtwork, "logoPositionX" | "logoPositionY">): { left: string; top: string; objectPosition: string } {
  const x = art.logoPositionX ?? 50, y = art.logoPositionY ?? 50;
  return { left: `${11 + (x - 50) / 50 * 11}%`, top: `${27 + (y - 50) / 50 * 27}%`, objectPosition: `${x}% ${y}%` };
}
export const LOGO_SCALE_MIN = 50;
export const LOGO_SCALE_MAX = 200;
export interface ThemeArtworkEditorAccess {
  title?(appId: number): string;
  getGeneral(): GameArtwork;
  getCustom(appId: number): GameArtwork | null;
  save(appId: number, value: GameArtwork | null): Promise<void>;
  images(appId: number): { source: "capsule" | "header" | "hero" | "logo"; url: string }[];
  games(): { appId: number; name: string }[];
}
export interface ThemeArtworkAccess {
  editor?: Readonly<ThemeArtworkEditorAccess>;
  get(appId: number): Readonly<GameArtwork> | null;
  subscribe(listener: () => void): () => void;
  edit(appId: number): boolean;
  /** Held by the theme host while a theme that owns covers (Duo) is mounted with this bridge. */
  attach?(): () => void;
}
export const DEFAULT_ARTWORK: GameArtwork = { source: "auto", image: null, positionX: 50, positionY: 50, showLogo: true, showTitle: true };
export function steamArtworkUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value, "https://steamloopback.host");
    return url.origin === "https://steamloopback.host" && /^\/(assets|customimages)\//.test(url.pathname) ? url.href : null;
  } catch { return null; }
}
