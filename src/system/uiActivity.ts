import { getGamepadNavigationTrees } from "@decky/ui";
import { setUiActive } from "../api";
import { onQamDocument } from "../qamDocument";

const RETRY_DELAYS_MS = [250, 1000] as const;

export interface UiActivityCoordinator {
  acquire(): () => void;
  shutdown(): void;
}

interface SteamOverlayActivityApi {
  RegisterForOverlayActivated(
    callback: (
      overlayProcessPid: number,
      appId: number,
      active: boolean,
      userInvoked?: boolean,
    ) => void,
  ): { unregister(): void };
}

type QamDocumentSubscriber = (callback: (doc: Document) => void) => () => void;

interface QamNavigationTree {
  id?: unknown;
  m_ID?: unknown;
  m_Root?: { m_element?: Element | null };
  Root?: { Element?: Element | null };
}

export function findQamNavigationDocument(
  candidates?: QamNavigationTree[],
): Document | null {
  try {
    const trees = candidates
      ?? getGamepadNavigationTrees() as QamNavigationTree[] | undefined;
    const tree = trees?.find((candidate) => {
      const id = candidate.id ?? candidate.m_ID;
      return typeof id === "string" && id.startsWith("QuickAccess");
    });
    const element = tree?.m_Root?.m_element ?? tree?.Root?.Element;
    return element?.ownerDocument ?? null;
  } catch {
    return null;
  }
}

export function createUiActivityCoordinator(
  write: (active: boolean) => Promise<unknown>,
): UiActivityCoordinator {
  let owners = 0;
  let desired = false;
  let applied: boolean | null = false;
  let running: Promise<void> | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let retryIndex = 0;
  let exhaustedTarget: boolean | null = null;

  const pump = (): void => {
    if (running || retryTimer || desired === applied || desired === exhaustedTarget) return;
    running = (async () => {
      while (desired !== applied) {
        const next = desired;
        try {
          await write(next);
        } catch {
          applied = null;
          if (desired !== next) {
            retryIndex = 0;
            exhaustedTarget = null;
            continue;
          }
          const delay = RETRY_DELAYS_MS[retryIndex];
          if (delay === undefined) {
            exhaustedTarget = next;
          } else {
            retryIndex += 1;
            retryTimer = setTimeout(() => {
              retryTimer = null;
              pump();
            }, delay);
          }
          return;
        }
        applied = next;
        retryIndex = 0;
        exhaustedTarget = null;
      }
    })().finally(() => {
      running = null;
      pump();
    });
  };

  const setDesired = (next: boolean): void => {
    if (next !== desired) {
      if (retryTimer) clearTimeout(retryTimer);
      retryTimer = null;
      retryIndex = 0;
      exhaustedTarget = null;
    }
    desired = next;
    pump();
  };

  return {
    acquire() {
      owners += 1;
      setDesired(true);
      let released = false;
      return () => {
        if (released) return;
        released = true;
        owners = Math.max(0, owners - 1);
        if (owners !== 0) return;
        queueMicrotask(() => {
          if (owners === 0) setDesired(false);
        });
      };
    },
    shutdown() {
      owners = 0;
      setDesired(false);
    },
  };
}

const uiActivity = createUiActivityCoordinator((active) => setUiActive(active));

export function acquireUiActivity(): () => void {
  return uiActivity.acquire();
}

export function createSteamOverlayActivityBridge(
  acquire: () => () => void,
  overlay: SteamOverlayActivityApi | undefined,
): () => void {
  if (!overlay?.RegisterForOverlayActivated) return () => {};
  let release: (() => void) | null = null;
  let registration: { unregister(): void };
  try {
    registration = overlay.RegisterForOverlayActivated((_pid, _appid, active) => {
      if (active) {
        if (release === null) release = acquire();
        return;
      }
      const current = release;
      release = null;
      current?.();
    });
  } catch {
    return () => {};
  }
  let stopped = false;
  return () => {
    if (stopped) return;
    stopped = true;
    try {
      registration.unregister();
    } catch {}
    const current = release;
    release = null;
    current?.();
  };
}

export function startSteamOverlayActivity(): () => void {
  const overlay = typeof SteamClient === "undefined"
    ? undefined
    : SteamClient.Overlay as unknown as SteamOverlayActivityApi;
  return createSteamOverlayActivityBridge(
    () => uiActivity.acquire(),
    overlay,
  );
}

export function createQamDocumentActivityBridge(
  acquire: () => () => void,
  subscribe: QamDocumentSubscriber,
  discover: () => Document | null = () => null,
): () => void {
  let current: Document | null = null;
  let release: (() => void) | null = null;
  let stopped = false;
  const releaseOwner = () => {
    const activeRelease = release;
    release = null;
    activeRelease?.();
  };
  const refresh = () => {
    if (stopped || !current) return;
    if (!current.hidden) {
      if (release === null) release = acquire();
      return;
    }
    releaseOwner();
  };
  const detach = () => {
    current?.removeEventListener("visibilitychange", refresh);
    current = null;
    releaseOwner();
  };
  const attach = (doc: Document) => {
    if (stopped || doc === current) return;
    detach();
    current = doc;
    current.addEventListener("visibilitychange", refresh);
    refresh();
  };
  const discovered = discover();
  if (discovered) attach(discovered);
  const unsubscribe = subscribe(attach);
  return () => {
    if (stopped) return;
    stopped = true;
    unsubscribe();
    detach();
  };
}

export function startQamDocumentActivity(): () => void {
  return createQamDocumentActivityBridge(
    () => uiActivity.acquire(),
    onQamDocument,
    findQamNavigationDocument,
  );
}

export function shutdownUiActivity(): void {
  uiActivity.shutdown();
}
