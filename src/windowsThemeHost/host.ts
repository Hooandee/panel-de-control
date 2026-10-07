import type { CssLoaderSnapshot } from "../themes/cssLoaderTypes";
import { evaluateThemeExtensionBundle, type ThemeExtensionExport } from "../themes/runtime/extensionHost";
import { startThemesRuntime } from "../themes/runtime/start";
import {
  configureThemeExtensionRpcHost,
  parseThemeExtensionPayload,
  type ThemeExtensionPayload,
} from "../themes/themeExtensionClient";

export const WINDOWS_THEME_HOST_VERSION = 1;

export interface WindowsThemeHostState {
  revision: number;
  snapshot: CssLoaderSnapshot;
  extensions: readonly ThemeExtensionPayload[];
}

export interface WindowsThemeHostStatus {
  hostVersion: number;
  revision: number;
  steamDocument: boolean;
  qamDocument: boolean;
  mounted: readonly string[];
  errors: readonly string[];
}

export interface WindowsThemeHost {
  readonly hostVersion: number;
  update(state: WindowsThemeHostState): WindowsThemeHostStatus;
  status(): WindowsThemeHostStatus;
  dispose(): void;
}

interface NavigationTree {
  m_ID?: string;
  Root?: { Element?: { ownerDocument?: Document | null } | null } | null;
}

interface FocusNavigationController {
  m_ActiveContext?: { m_rgGamepadNavigationTrees?: readonly NavigationTree[] } | null;
  m_LastActiveContext?: { m_rgGamepadNavigationTrees?: readonly NavigationTree[] } | null;
}

const MAX_ERRORS = 20;
const QAM_POLL_MS = 2_000;
const DOCUMENT_POLL_MS = 2_000;

function navigationTrees(scope: typeof globalThis): readonly NavigationTree[] {
  const global = scope as typeof globalThis & {
    GamepadNavTree?: { m_context?: { m_controller?: FocusNavigationController } };
    FocusNavController?: FocusNavigationController;
  };
  const controller = global.GamepadNavTree?.m_context?.m_controller ?? global.FocusNavController;
  const context = controller?.m_ActiveContext ?? controller?.m_LastActiveContext;
  return context?.m_rgGamepadNavigationTrees ?? [];
}

function treeDocument(scope: typeof globalThis, matches: (id: string) => boolean): Document | null {
  const tree = navigationTrees(scope).find((candidate) => matches(candidate.m_ID ?? ""));
  return tree?.Root?.Element?.ownerDocument ?? null;
}

export function findBigPictureDocument(scope: typeof globalThis = globalThis): Document | null {
  return treeDocument(scope, (id) => id === "GamepadUI_Full_Root" || id === "root_1_");
}

export function findQuickAccessDocument(scope: typeof globalThis = globalThis): Document | null {
  return treeDocument(scope, (id) => id.startsWith("QuickAccess"));
}

function extensionKey(payload: Pick<ThemeExtensionPayload, "catalogId" | "version">): string {
  return `${payload.catalogId}@${payload.version}`;
}

export function createWindowsThemeHost(scope: typeof globalThis = globalThis): WindowsThemeHost {
  let state: WindowsThemeHostState = {
    revision: 0,
    snapshot: { status: "missing", themes: [] },
    extensions: [],
  };
  const listeners = new Set<() => void>();
  const mounted = new Set<string>();
  const errors: string[] = [];
  const recordError = (code: string) => {
    errors.push(code);
    if (errors.length > MAX_ERRORS) errors.shift();
  };

  const releaseRpcHost = configureThemeExtensionRpcHost({
    list: async () => state.extensions.map(({ source: _source, ...descriptor }) => descriptor),
    load: async (catalogId, version) => {
      const payload = state.extensions.find(
        (candidate) => candidate.catalogId === catalogId && candidate.version === version,
      );
      if (!payload) throw new Error("Theme extension is not installed");
      return payload;
    },
  });

  const trackMounts = (source: string): ThemeExtensionExport => {
    const extension = evaluateThemeExtensionBundle(source);
    const payload = state.extensions.find((candidate) => candidate.source === source);
    const key = payload ? extensionKey(payload) : "unknown";
    return Object.freeze({
      ...extension,
      mount: (context: never) => {
        const stop = extension.mount(context);
        mounted.add(key);
        return () => {
          mounted.delete(key);
          stop();
        };
      },
    }) as ThemeExtensionExport;
  };

  let qamTimer: ReturnType<typeof setInterval> | undefined;
  const qamListeners = new Set<(doc: Document) => void>();
  let lastQamDocument: Document | null = null;
  const pollQam = () => {
    const doc = findQuickAccessDocument(scope);
    if (!doc || doc === lastQamDocument) return;
    lastQamDocument = doc;
    for (const listener of [...qamListeners]) listener(doc);
  };

  const stopRuntime = startThemesRuntime({
    client: {
      getSnapshot: () => ({ snapshot: state.snapshot }),
      subscribe: (listener) => {
        listeners.add(listener);
        const documentPoll = setInterval(listener, DOCUMENT_POLL_MS);
        return () => {
          clearInterval(documentPoll);
          listeners.delete(listener);
        };
      },
      refresh: async () => {},
    },
    getSteamDocument: () => findBigPictureDocument(scope),
    getQamDocument: () => findQuickAccessDocument(scope),
    subscribeQamDocument: (listener) => {
      qamListeners.add(listener);
      qamTimer ??= setInterval(pollQam, QAM_POLL_MS);
      return () => {
        qamListeners.delete(listener);
        if (qamListeners.size === 0 && qamTimer !== undefined) {
          clearInterval(qamTimer);
          qamTimer = undefined;
        }
      };
    },
    evaluate: trackMounts,
    log: recordError,
  });

  const status = (): WindowsThemeHostStatus => ({
    hostVersion: WINDOWS_THEME_HOST_VERSION,
    revision: state.revision,
    steamDocument: findBigPictureDocument(scope) !== null,
    qamDocument: findQuickAccessDocument(scope) !== null,
    mounted: [...mounted].sort(),
    errors: [...errors],
  });

  return Object.freeze({
    hostVersion: WINDOWS_THEME_HOST_VERSION,
    update(next: WindowsThemeHostState) {
      if (next.revision <= state.revision) return status();
      state = {
        revision: next.revision,
        snapshot: next.snapshot,
        extensions: next.extensions.map(parseThemeExtensionPayload),
      };
      for (const listener of [...listeners]) listener();
      return status();
    },
    status,
    dispose() {
      stopRuntime();
      releaseRpcHost();
      if (qamTimer !== undefined) clearInterval(qamTimer);
      listeners.clear();
      qamListeners.clear();
    },
  });
}
