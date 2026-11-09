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
 * The logo box (78 % x 36 %) slides with the position and the logo moves inside it the same way. Across, 0 and 100
 * reach the edges; down, the box goes from the top to 54 %, the band covers keep for the logo, and 50 is where it
 * always sat. Themes must reproduce this placement.
 */
export function logoPlacement(art: Pick<GameArtwork, "logoPositionX" | "logoPositionY">): { left: string; top: string; objectPosition: string } {
  const x = art.logoPositionX ?? 50, y = art.logoPositionY ?? 50;
  return { left: `${x * 11 / 50}%`, top: `${y * 27 / 50}%`, objectPosition: `${x}% ${y}%` };
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
