import { recordUiEvent } from "../system/uiEvents";
import { DEFAULT_ARTWORK, type GameArtwork, type ThemeArtworkAccess } from "./artwork";

interface ArtworkRpcHost {
  read(): Promise<Record<string, GameArtwork>>;
  write(id: number, value: GameArtwork | null): Promise<{ ok: boolean; error?: string }>;
}
let host: ArtworkRpcHost | null = null;
let writes: Promise<void> = Promise.resolve();
export function configureArtworkHost(next: ArtworkRpcHost): () => void {
  if (host !== next) { cache = {}; ready = false; request = null; writes = Promise.resolve(); }
  host = next;
  return () => { if (host === next) { host = null; cache = {}; ready = false; request = null; } };
}
let cache: Record<string, GameArtwork> = {};
let request: Promise<void> | null = null;
let ready = false;
const listeners = new Set<() => void>();
let editor: ((id: number) => boolean) | null = null;
const notify = () => {
  for (const listener of listeners) {
    try { listener(); } catch { recordUiEvent("themes", "artwork_listener_failed", {}, false); }
  }
};
export function loadArtwork(): Promise<void> {
  if (ready) return Promise.resolve();
  if (!host) return Promise.reject(new Error("artwork_unavailable"));
  const currentHost = host;
  if (!request) request = Promise.resolve().then(() => currentHost.read()).then((value) => {
    if (host !== currentHost) throw new Error("artwork_host_replaced");
    cache = value;
    ready = true;
    notify();
  }).catch((error) => {
    recordUiEvent("themes", "artwork_load_failed", {}, false);
    throw error;
  }).finally(() => { if (host === currentHost) request = null; });
  return request;
}
export async function saveArtwork(id: number, value: GameArtwork | null): Promise<void> {
  if (id === 0 && value?.image != null) throw new Error("invalid_general_image");
  await loadArtwork();
  if (!host) throw new Error("artwork_unavailable");
  const currentHost = host;
  const savedValue = value ? { ...value } : null;
  const write = writes.catch(() => {}).then(async () => {
    if (host !== currentHost) throw new Error("artwork_host_replaced");
    const result = await currentHost.write(id, savedValue);
    if (host !== currentHost) throw new Error("artwork_host_replaced");
    if (!result.ok) throw new Error(result.error ?? "save_failed");
    if (savedValue) cache = { ...cache, [id]: savedValue };
    else { cache = { ...cache }; delete cache[id]; }
    notify();
  });
  writes = write;
  return write;
}
export function getGeneralArtwork(): GameArtwork { return { ...(cache[0] ?? { ...DEFAULT_ARTWORK, showTitle: false }) }; }
export function getCustomArtwork(id: number): GameArtwork | null { return cache[id] ? { ...cache[id] } : null; }
export function saveGeneralArtwork(value: GameArtwork | null): Promise<void> { return saveArtwork(0, value); }
export function registerArtworkEditor(open: (id: number) => boolean): () => void {
  editor = open;
  return () => { if (editor === open) editor = null; };
}
let attachedThemes = 0;
/** True while a cover-owning theme is mounted with the bridge: only then do game menus offer the cover editor. */
export function artworkThemeActive(): boolean { return attachedThemes > 0; }
export const artworkAccess: ThemeArtworkAccess = Object.freeze({
  get: (id: number) => { const value = cache[id] ?? cache[0]; return value ? Object.freeze({ ...value }) : null; },
  subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
  edit: (id: number) => editor?.(id) ?? false,
  attach: () => {
    attachedThemes++;
    let released = false;
    return () => { if (!released) { released = true; attachedThemes--; } };
  },
});

export function startArtworkHydration(): () => void {
  const delays = [1000, 3000, 10000];
  let stopped = false;
  let retry = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const attempt = () => {
    if (stopped) return;
    void loadArtwork().catch(() => {
      if (!stopped && retry < delays.length) timer = setTimeout(attempt, delays[retry++]);
    });
  };
  attempt();
  return () => {
    stopped = true;
    if (timer !== undefined) clearTimeout(timer);
  };
}
