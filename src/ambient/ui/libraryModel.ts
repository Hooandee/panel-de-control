import type { Favorite, MediaKind } from "../core/types";
import { parseEmbedStream } from "../core/streams";
import { isHls, parseYouTube } from "../core/youtube";
import type { CollectionEntry, ScanResult } from "../steam/rpc";

export type LibraryPurpose = "background" | "playback";
export interface LibraryItem { credit?: string; ref: string; kind: MediaKind; name: string; collection: string }
export type LibraryPhoto = LibraryItem & { kind: "image" };

export const acceptsMedia = (kind: MediaKind, purpose: LibraryPurpose): boolean => purpose === "background" ? kind !== "audio" : kind !== "image";

export function linkKind(url: string): MediaKind | null {
  const path = url.split(/[?#]/)[0].toLowerCase();
  if (/\.(?:jpg|jpeg|png|webp|gif|bmp|avif)$/.test(path)) return "image";
  if (/\.(?:mp4|webm|mkv|mov|m4v)$/.test(path)) return "video";
  if (/\.(?:mp3|ogg|opus|flac|wav|m4a|aac)$/.test(path)) return "audio";
  return null;
}

export function libraryFavorites(background: Favorite[], playback: Favorite[], purpose: LibraryPurpose): Favorite[] {
  const visual = new Set(background.map((f) => f.url));
  const unique = new Map<string, Favorite>();
  for (const favorite of [...background, ...playback]) if (!unique.has(favorite.url)) unique.set(favorite.url, favorite);
  return [...unique.values()].filter((f) => {
    if (parseYouTube(f.url) || parseEmbedStream(f.url) || isHls(f.url)) return purpose === "playback";
    const kind = linkKind(f.url);
    return kind ? acceptsMedia(kind, purpose) : purpose === "background" ? visual.has(f.url) : !visual.has(f.url) || playback.some((p) => p.url === f.url);
  });
}

export function visualSources(sources: CollectionEntry[], scan: ScanResult | null, background: Favorite[], playback: Favorite[]): CollectionEntry[] {
  const links = new Set(libraryFavorites(background, playback, "background").map((f) => f.url));
  return sources.filter((source) => {
    if (source.kind === "suggested") return true;
    if (source.kind === "favorite") return !!source.url && links.has(source.url);
    return (scan?.library?.[source.id] ?? scan?.collections[source.id] ?? []).some((item) => acceptsMedia(item.kind, "background"));
  });
}

export function preferredSource(sources: CollectionEntry[], scan: ScanResult | null, purpose: LibraryPurpose, ref?: string, collection?: string): string | null {
  if (collection && sources.some((source) => source.id === collection)) return collection;
  if (ref) {
    const matching = sources.filter((source) => (scan?.library?.[source.id] ?? scan?.collections[source.id] ?? []).some((item) => item.id === ref));
    const source = matching.find((source) => source.kind === "folder") ?? matching[0];
    if (source) return source.id;
  }
  return (purpose === "playback" ? sources.find((source) => source.id === "known.music") : null)?.id ?? sources[0]?.id ?? null;
}

export function photoSelection(refs: readonly string[], items: readonly LibraryItem[]): Map<string, LibraryPhoto> {
  const available = new Map<string, LibraryPhoto>();
  for (const item of items) if (item.kind === "image" && !available.has(item.ref)) available.set(item.ref, { ...item, kind: "image" });
  return new Map(refs.flatMap((ref) => {
    const item = available.get(ref);
    return item ? [[ref, item] as const] : [];
  }));
}
