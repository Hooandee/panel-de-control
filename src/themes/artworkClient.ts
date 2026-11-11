import { recordUiEvent } from "../system/uiEvents";
import { DEFAULT_ARTWORK, type GameArtwork, type ThemeArtworkAccess, type ThemeArtworkStore } from "./artwork";

export interface ArtworkRpcHost {
  read(): Promise<Record<string, GameArtwork>>;
  write(id: number, value: GameArtwork | null): Promise<{ ok: boolean; error?: string }>;
}

export interface ArtworkStore {
  configureHost(next: ArtworkRpcHost): () => void;
  load(): Promise<void>;
  save(id: number, value: GameArtwork | null): Promise<void>;
  getGeneral(): GameArtwork;
  getCustom(id: number): GameArtwork | null;
  registerEditor(open: (id: number) => boolean): () => void;
  themeActive(): boolean;
  startHydration(): () => void;
  readonly access: ThemeArtworkAccess;
}

const HYDRATION_DELAYS_MS = [1000, 3000, 10000];

/** One theme's covers: its own cache, listeners, editor and backend store. */
export function createArtworkStore(name: ThemeArtworkStore, options: { hydrateOnAttach?: boolean } = {}): ArtworkStore {
  let host: ArtworkRpcHost | null = null;
  let writes: Promise<void> = Promise.resolve();
  let cache: Record<string, GameArtwork> = {};
  let request: Promise<void> | null = null;
  let ready = false;
  let editor: ((id: number) => boolean) | null = null;
  let attachedThemes = 0;
  let stopAttachedHydration: (() => void) | null = null;
  const listeners = new Set<() => void>();

  const notify = () => {
    for (const listener of listeners) {
      try { listener(); } catch { recordUiEvent("themes", "artwork_listener_failed", { store: name }, false); }
    }
  };

  const configureHost = (next: ArtworkRpcHost): () => void => {
    if (host !== next) { cache = {}; ready = false; request = null; writes = Promise.resolve(); }
    host = next;
    return () => { if (host === next) { host = null; cache = {}; ready = false; request = null; } };
  };

  const load = (): Promise<void> => {
    if (ready) return Promise.resolve();
    if (!host) return Promise.reject(new Error("artwork_unavailable"));
    const currentHost = host;
    if (!request) request = Promise.resolve().then(() => currentHost.read()).then((value) => {
      if (host !== currentHost) throw new Error("artwork_host_replaced");
      cache = value;
      ready = true;
      notify();
    }).catch((error) => {
      recordUiEvent("themes", "artwork_load_failed", { store: name }, false);
      throw error;
    }).finally(() => { if (host === currentHost) request = null; });
    return request;
  };

  const save = async (id: number, value: GameArtwork | null): Promise<void> => {
    if (id === 0 && value?.image != null) throw new Error("invalid_general_image");
    await load();
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
  };

  const startHydration = (): () => void => {
    let stopped = false;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const attempt = () => {
      if (stopped) return;
      void load().catch(() => {
        if (!stopped && retry < HYDRATION_DELAYS_MS.length) timer = setTimeout(attempt, HYDRATION_DELAYS_MS[retry++]);
      });
    };
    attempt();
    return () => {
      stopped = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  };

  const access: ThemeArtworkAccess = Object.freeze({
    get: (id: number) => { const value = cache[id] ?? cache[0]; return value ? Object.freeze({ ...value }) : null; },
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    edit: (id: number) => editor?.(id) ?? false,
    attach: () => {
      attachedThemes++;
      if (options.hydrateOnAttach && !stopAttachedHydration) stopAttachedHydration = startHydration();
      let released = false;
      return () => {
        if (released) return;
        released = true;
        attachedThemes--;
        if (attachedThemes === 0 && stopAttachedHydration) { stopAttachedHydration(); stopAttachedHydration = null; }
      };
    },
  });

  return {
    configureHost,
    load,
    save,
    getGeneral: () => ({ ...(cache[0] ?? { ...DEFAULT_ARTWORK, showTitle: false }) }),
    getCustom: (id: number) => cache[id] ? { ...cache[id] } : null,
    registerEditor: (open) => {
      editor = open;
      return () => { if (editor === open) editor = null; };
    },
    themeActive: () => attachedThemes > 0,
    startHydration,
    access,
  };
}

// Duo hydrates at startup (its covers also feed the game menus); Vida's store is read only while Vida is mounted.
const duo = createArtworkStore("duo");
export const vidaArtwork = createArtworkStore("vida", { hydrateOnAttach: true });

export const configureArtworkHost = duo.configureHost;
export const loadArtwork = duo.load;
export const saveArtwork = duo.save;
export const getGeneralArtwork = duo.getGeneral;
export const getCustomArtwork = duo.getCustom;
export function saveGeneralArtwork(value: GameArtwork | null): Promise<void> { return duo.save(0, value); }
export const registerArtworkEditor = duo.registerEditor;
/** True while a cover-owning theme is mounted with the bridge: only then do game menus offer the cover editor. */
export const artworkThemeActive = duo.themeActive;
export const artworkAccess: ThemeArtworkAccess = duo.access;
export const startArtworkHydration = duo.startHydration;
