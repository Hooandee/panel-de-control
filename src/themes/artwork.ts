export interface GameArtwork {
  source: "auto" | "capsule" | "header" | "hero";
  image: string | null;
  positionX: number;
  positionY: number;
  showLogo: boolean;
  showTitle: boolean;
}
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
