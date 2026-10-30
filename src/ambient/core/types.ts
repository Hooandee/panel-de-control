export type ClaimOwner = "panel" | "theme" | "other";
export type InGameAction = "pause" | "continue" | "duck";
export type GameArtMode = "mine" | "blend" | "game";
export type MediaKind = "image" | "video" | "audio";
export type RepeatMode = "all" | "one" | "off";

export interface QueuedTrack {
  id: string;
  url: string;
  title: string;
  subtitle: string;
  art: string;
  kind: "audio" | "video";
  live: boolean;
}

export interface AmbientSettings {
  version: 1;
  background: {
    enabled: boolean;
    collections: string[];
    intervalSec: 30 | 60 | 300 | 900 | 3600;
    onReturnHome: boolean;
    order: "sequential" | "shuffle";
    transition: "fade" | "kenburns";
    gameArt: GameArtMode;
    library: boolean;
    perGame: Record<string, string>;
    /** The one background shown when it should not rotate; empty while rotating. */
    pinned: string;
    selectedRefs?: string[];
    /** On Home, the selected game's official trailer plays as the background and its soundtrack plays. */
    gameTrailers: boolean;
    gameThemes: boolean;
    lowBatteryPercent: number;
    optimizeVideos: boolean;
    videoQuality: VideoQuality;
  };
  music: {
    enabled: boolean;
    source: "music" | "radio";
    volume: number;
    inGameMusic: InGameAction;
    inGameRadio: InGameAction;
    qamPlayer: boolean;
    /** The video was showing when the listener last chose; it comes back after a restart. */
    videoOn: boolean;
    overlay: OverlayMode;
    overlayCorner: OverlayCorner;
    videoSize: VideoSize;
    /** Width of the video card as a percentage of the screen. */
    videoScale: number;
    /** In-game volume per source, 0 pauses and 100 keeps it as is. */
    inGameMusicLevel: number;
    inGameRadioLevel: number;
    /** While playing a game: Ambiente's media volume (0 pauses) and the game's own volume. */
    inGameMediaLevel: number;
    inGameGameLevel: number;
    folders: string[];
    lastTrack: { id: string; position: number } | null;
    repeat: RepeatMode;
    shuffle: boolean;
    /** What was queued, in play order; local songs are resolved again because their URL carries a session token. */
    queue: QueuedTrack[];
    stationId: string | null;
  };
  collections: { removedSuggested: string[]; favorites: Favorite[]; folders: string[] };
  radio: { removedSuggested: string[]; favorites: Favorite[]; playlists: Playlist[] };
  claims: Record<string, ClaimOwner>;
}

export interface Favorite {
  id: string;
  name: string;
  url: string;
  art?: string;
  subtitle?: string;
}

export interface MediaItem {
  id: string;
  name: string;
  kind: MediaKind;
  size: number;
  mtime: number;
}

export interface Station {
  id: string;
  name: string;
  url: string;
  favicon: string;
  country: string;
  countryCode: string;
  tags: string[];
  codec: string;
  bitrate: number;
  geo?: [number, number];
}

export interface RadioCountry {
  code: string;
  name: string;
  count: number;
}

export interface RadioTag {
  name: string;
  count: number;
}

export interface RadioCatalog {
  countries: RadioCountry[];
  tags: RadioTag[];
  error?: "catalog_unreachable";
}

export type RadioOrder = "popular" | "trending" | "votes" | "quality";

export interface RadioFilters {
  name?: string;
  country?: string;
  tag?: string;
  minBitrate?: number;
  order?: RadioOrder;
  limit?: number;
  offset?: number;
  hasGeo?: boolean;
  near?: { lat: number; lon: number; radiusKm: number };
}

export type OverlayMode = "off" | "peek" | "always";
export type OverlayCorner = "top-left" | "top-right" | "bottom-left" | "bottom-right";
export type VideoSize = "small" | "medium" | "large";

export interface Playlist {
  id: string;
  name: string;
  url: string;
}

export interface Channel {
  id: string;
  name: string;
  url: string;
  logo: string;
  group: string;
}

export interface PlaylistContents {
  id: string;
  channels: Channel[];
  error?: string;
}

export type VideoQuality = "fluid" | "saver" | "sharp";
