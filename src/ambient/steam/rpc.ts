import { callable } from "@decky/api";

import type { AmbientSettings, MediaItem, PlaylistContents, RadioCatalog, RadioFilters, Station } from "../core/types";
import type { GameMedia } from "./gameMedia";

export interface CollectionEntry {
  id: string;
  kind: "known" | "screenshots" | "suggested" | "folder" | "favorite";
  source?: string;
  name?: string;
  url?: string;
  path?: string;
}

export interface AmbientState {
  settings: AmbientSettings;
  knownFolders: { images: string[]; videos: string[]; music: string[] };
  collections: CollectionEntry[];
  mediaServer: "loopback" | "stopped";
}

export interface ScanResult {
  library?: Record<string, MediaItem[]>;
  collections: Record<string, MediaItem[]>;
  music: MediaItem[];
  truncated: boolean;
}

export interface RemoteImage {
  url: string;
  title: string;
  credit: string;
}

export type Served = { id: string; url: string | null } | { error: string };

export const getAmbientState = callable<[], AmbientState>("get_ambient_state");
export const saveAmbientSettings = callable<[settings: AmbientSettings], AmbientSettings>("save_ambient_settings");
export const scanAmbientSources = callable<[], ScanResult>("scan_ambient_sources");
export const getAmbientMediaUrl = callable<[mediaId: string], string | null>("get_ambient_media_url");
/** URLs of one theme picture per screen size bucket ("1280", "1920", "2560"). */
export type ThemeImageUrls = Record<string, string>;
export interface ThemeImageEntry { urls: ThemeImageUrls; owners: string[] }
export const registerAmbientThemeImage = callable<[mediaId: string, owner: string, maxSide: number | null], { ref: string; urls: ThemeImageUrls } | { error: string }>("register_ambient_theme_image");
/** The refs `owner` (a theme's catalog id) still shows; answers the refs the backend forgot. */
export const keepAmbientThemeImages = callable<[owner: string, refs: string[]], string[]>("keep_ambient_theme_images");
export const getAmbientThemeImages = callable<[], Record<string, ThemeImageEntry>>("get_ambient_theme_images");
export const getAmbientVideoPage = callable<[], string | null>("get_ambient_video_page");
export const addAmbientPlaylist = callable<[url: string, name: string], AmbientSettings | null>("add_ambient_playlist");
export const inspectAmbientLink = callable<[url: string], { kind: "list" | "stream" | "unknown" }>("inspect_ambient_link");
export const removeAmbientPlaylist = callable<[playlistId: string], AmbientSettings | null>("remove_ambient_playlist");
export const getAmbientPlaylist = callable<[playlistId: string], PlaylistContents | null>("get_ambient_playlist");
export const addAmbientFolder = callable<[path: string, scope: "background" | "music" | "library"], AmbientSettings | null>("add_ambient_folder");
export const addAmbientFavorite = callable<[scope: "background" | "radio", url: string, name: string, art: string, subtitle: string], AmbientSettings | null>("add_ambient_favorite");
export const removeAmbientItem = callable<[scope: "background" | "radio" | "music" | "library", itemId: string], AmbientSettings | null>("remove_ambient_item");
export const restoreAmbientSuggested = callable<[scope: "background" | "radio", itemId: string], AmbientSettings | null>("restore_ambient_suggested");
export const getAmbientGameMedia = callable<[appid: string, name: string, store: boolean], GameMedia>("get_ambient_game_media");
export const setAmbientGameVolume = callable<[percent: number], { supported: boolean; streams: number }>("set_ambient_game_volume");
export const getAmbientRemoteFeed = callable<[source: string, market: string], RemoteImage[]>("get_ambient_remote_feed");
export const cacheAmbientRemote = callable<[url: string, collection?: string], Served>("cache_ambient_remote");
export const reconcileAmbientCache = callable<[], boolean>("reconcile_ambient_cache");
export const optimizeAmbientMedia = callable<[mediaId: string, height: number, fps: number, codec?: "h264" | "vp9"], Served & { encoder?: string }>("optimize_ambient_media");
export const searchAmbientRadio = callable<[name: string, country: string, tag: string], Station[]>("search_ambient_radio");
export const getAmbientSuggestedStations = callable<[], Station[]>("get_ambient_suggested_stations");
export const resolveAmbientRadio = callable<[stationId: string], Station | null>("resolve_ambient_radio");
export const getAmbientRadioCatalog = callable<[forceRefresh?: boolean], RadioCatalog>("get_ambient_radio_catalog");
export const discoverAmbientRadio = callable<[filters: RadioFilters], Station[]>("discover_ambient_radio");
export const cancelAmbientJobs = callable<[], boolean>("cancel_ambient_jobs");
export const recordAmbientEvent = callable<[kind: string, detail: string], boolean>("record_ambient_event");
export const checkAmbientAudio = callable<[detail: string], boolean>("check_ambient_audio");

export type ShareSession = { url: string; expiresIn: number } | { error: string };
export const startAmbientShare = callable<[texts: Record<string, string>], ShareSession>("start_ambient_share");
export const takeAmbientShared = callable<[], { links: string[]; active: boolean }>("take_ambient_shared");
export const stopAmbientShare = callable<[], boolean>("stop_ambient_share");
