import { findModuleByExport, findModuleExport } from "@decky/ui";

import {
  selectSteamPerformanceComponents,
  SteamPerformanceComponents,
  SteamPerformanceStoreView,
} from "./performanceSurface";
import {
  recordSteamPerformanceDiagnostic,
  resetSteamPerformanceDiagnostics,
  steamPerformanceError,
} from "./performanceDiagnostics";

interface SteamPerformanceStore extends SteamPerformanceStoreView {
  nCurrentGameID?: string | number;
  nActiveProfileGameID?: string | number;
  SetGameSpecificProfileEnabled?: (enabled: boolean) => unknown;
  SetVRREnabled?: (enabled: boolean) => unknown;
  SetSplitScalingScaler?: (value: number) => unknown;
  ResetCurrentPerfProfileSettings?: () => unknown;
}

interface SteamPerformanceStoreClass {
  Get: () => unknown;
  prototype: SteamPerformanceStore;
}

interface SteamPerformanceRegistration {
  unregister?: () => void;
}

interface SteamPerformanceClient {
  System?: {
    Perf?: {
      RegisterForStateChanges?: (
        callback: () => void,
      ) => SteamPerformanceRegistration | void;
    };
  };
}

interface SteamWebpackRuntime {
  (moduleId: string): unknown;
  m?: Record<string, unknown>;
}

interface SteamWebpackChunks {
  push(chunk: [unknown[], Record<string, never>, (runtime: SteamWebpackRuntime) => void]): unknown;
}

let cachedRuntime: {
  chunks: SteamWebpackChunks;
  runtime: SteamWebpackRuntime;
  store?: SteamPerformanceStore;
  components?: SteamPerformanceComponents;
} | null = null;
let cachedLegacyComponents: SteamPerformanceComponents | null = null;
let legacyProfileRequests = new WeakMap<object, string>();
const STEAM_GLOBAL_PROFILE_GAME_ID = "769";

const appIdFromSteamGameId = (gameId: string): string | null => {
  if (typeof BigInt !== "function") return null;
  try {
    const value = BigInt(gameId);
    const uint32Mask = BigInt(0xffffffff);
    if (value <= uint32Mask) return value.toString();
    const type = (value >> BigInt(24)) & BigInt(0xff);
    return type === BigInt(2)
      ? ((value >> BigInt(32)) & uint32Mask).toString()
      : (value & BigInt(0xffffff)).toString();
  } catch {
    return null;
  }
};

export function resetSteamPerformanceRuntimeCache(): void {
  cachedRuntime = null;
  cachedLegacyComponents = null;
  legacyProfileRequests = new WeakMap<object, string>();
  resetSteamPerformanceDiagnostics();
}

const sourceOf = (candidate: unknown): string => {
  if (typeof candidate !== "function") return "";
  try {
    return candidate.toString();
  } catch {
    return "";
  }
};

const isResetExport = (candidate: unknown): boolean => {
  const source = sourceOf(candidate);
  return source.includes("#QuickAccess_Tab_Perf_ResetToDefault")
    && source.includes("ResetCurrentPerfProfileSettings");
};

const asModuleExports = (candidate: unknown): Record<string, unknown> => {
  if ((typeof candidate !== "object" || candidate === null) && typeof candidate !== "function") {
    return {};
  }
  return candidate as Record<string, unknown>;
};

const currentSteamRuntime = (): SteamWebpackRuntime | null => {
  const chunks = (window as unknown as { webpackChunksteamui?: SteamWebpackChunks })
    .webpackChunksteamui;
  if (!chunks || typeof chunks.push !== "function") {
    cachedRuntime = null;
    recordSteamPerformanceDiagnostic("runtime", {
      status: "unavailable",
      reason: "webpack_chunks_missing",
    });
    return null;
  }
  if (cachedRuntime?.chunks === chunks) return cachedRuntime.runtime;

  let runtime: SteamWebpackRuntime | null = null;
  try {
    chunks.push([
      [`pdc-steam-performance-${Date.now()}`],
      {},
      (candidate) => { runtime = candidate; },
    ]);
  } catch (error) {
    recordSteamPerformanceDiagnostic("runtime", {
      status: "capture_failed",
      error: steamPerformanceError(error),
    });
    return null;
  }
  const resolved = runtime as SteamWebpackRuntime | null;
  if (!resolved?.m) {
    recordSteamPerformanceDiagnostic("runtime", {
      status: "unavailable",
      reason: "module_table_missing",
    });
    return null;
  }
  cachedRuntime = { chunks, runtime: resolved };
  recordSteamPerformanceDiagnostic("runtime", {
    status: "ready",
    module_count: Object.keys(resolved.m).length,
  });
  return resolved;
};

const factoryIncludes = (factory: unknown, ...tokens: string[]): boolean => {
  if (typeof factory !== "function") return false;
  try {
    const source = Function.prototype.toString.call(factory);
    return tokens.every((token) => source.includes(token));
  } catch {
    return false;
  }
};

const componentCount = (components: SteamPerformanceComponents): number => (
  Object.keys(components).length
);

const componentsFromModule = (candidate: unknown): SteamPerformanceComponents => {
  const module = asModuleExports(candidate);
  const nestedDefault = asModuleExports(module.default);
  const direct = selectSteamPerformanceComponents(module);
  const nested = selectSteamPerformanceComponents(nestedDefault);
  return componentCount(nested) > componentCount(direct) ? nested : direct;
};

const discoverCurrentRuntimeComponents = (): SteamPerformanceComponents | null => {
  const runtime = currentSteamRuntime();
  if (!runtime?.m) return null;
  if (cachedRuntime?.runtime === runtime && cachedRuntime.components) {
    return cachedRuntime.components;
  }
  const candidates: SteamPerformanceComponents[] = [];
  for (const [moduleId, factory] of Object.entries(runtime.m)) {
    if (!factoryIncludes(
      factory,
      "#QuickAccess_Tab_Perf_ResetToDefault",
      "ResetCurrentPerfProfileSettings",
    )) continue;
    try {
      const components = componentsFromModule(runtime(moduleId));
      if (componentCount(components) > 0) candidates.push(components);
    } catch {
      continue;
    }
  }
  if (candidates.length !== 1) {
    recordSteamPerformanceDiagnostic("components", {
      status: candidates.length === 0 ? "not_found" : "ambiguous",
      source: "current_runtime",
      candidate_count: candidates.length,
    });
    return {};
  }
  const [components] = candidates;
  recordSteamPerformanceDiagnostic("components", {
    status: "ready",
    source: "current_runtime",
    candidate_count: 1,
    component_ids: Object.keys(components).sort(),
  });
  if (cachedRuntime?.runtime === runtime) cachedRuntime.components = components;
  return components;
};

export function discoverSteamPerformanceComponents(): SteamPerformanceComponents {
  const current = discoverCurrentRuntimeComponents();
  if (current !== null) return current;
  if (cachedLegacyComponents) return cachedLegacyComponents;

  let snapshot: SteamPerformanceComponents = {};
  try {
    const module = findModuleByExport(isResetExport);
    snapshot = componentsFromModule(module);
  } catch {
    snapshot = {};
  }
  recordSteamPerformanceDiagnostic("components", {
    status: componentCount(snapshot) > 0 ? "ready" : "not_found",
    source: "legacy_snapshot",
    candidate_count: componentCount(snapshot) > 0 ? 1 : 0,
    component_ids: Object.keys(snapshot).sort(),
  });
  if (componentCount(snapshot) > 0) cachedLegacyComponents = snapshot;
  return snapshot;
}

const asStore = (candidate: unknown): SteamPerformanceStore | null => {
  if ((typeof candidate !== "object" || candidate === null) && typeof candidate !== "function") {
    return null;
  }
  return candidate as SteamPerformanceStore;
};

const isStoreClass = (candidate: unknown): candidate is SteamPerformanceStoreClass => {
  if (typeof candidate !== "function") return false;
  const type = candidate as unknown as SteamPerformanceStoreClass;
  return typeof type.Get === "function"
    && typeof type.prototype?.ResetCurrentPerfProfileSettings === "function";
};

const storeSingleton = (candidate: unknown): SteamPerformanceStore | null => {
  const direct = asStore(candidate);
  if (direct?.msgLimits) return direct;
  if (typeof candidate !== "function") return null;
  try {
    return asStore((candidate as unknown as { Get?: () => unknown }).Get?.());
  } catch {
    return null;
  }
};

const storeClassFromModule = (candidate: unknown): SteamPerformanceStoreClass | null => {
  const module = asModuleExports(candidate);
  const candidates = [candidate, module.default, ...Object.values(module)];
  return candidates.find(isStoreClass) ?? null;
};

const storeProfileIds = (store: SteamPerformanceStore) => ({
  current_game_id: store.nCurrentGameID === undefined ? null : String(store.nCurrentGameID),
  active_profile_game_id:
    store.nActiveProfileGameID === undefined ? null : String(store.nActiveProfileGameID),
});

const recordResolvedStore = (
  source: "global" | "current_runtime" | "legacy_snapshot",
): void => {
  recordSteamPerformanceDiagnostic("store", {
    status: "ready",
    source,
  });
};

const resolveCurrentRuntimeStore = (): SteamPerformanceStore | null | undefined => {
  const runtime = currentSteamRuntime();
  if (!runtime?.m) return undefined;
  if (cachedRuntime?.runtime === runtime && cachedRuntime.store?.msgLimits) {
    return cachedRuntime.store;
  }
  const candidates = new Set<SteamPerformanceStore>();
  for (const [moduleId, factory] of Object.entries(runtime.m)) {
    if (!factoryIncludes(
      factory,
      "ResetCurrentPerfProfileSettings",
    )) continue;
    try {
      const store = storeSingleton(storeClassFromModule(runtime(moduleId)));
      if (store?.msgLimits) candidates.add(store);
    } catch {
      continue;
    }
  }
  if (candidates.size === 0) return undefined;
  if (candidates.size > 1) {
    recordSteamPerformanceDiagnostic("store", {
      status: "ambiguous",
      source: "current_runtime",
      candidate_count: candidates.size,
    });
    return null;
  }
  const [store] = candidates;
  if (cachedRuntime?.runtime === runtime) cachedRuntime.store = store;
  return store;
};

export function resolveSteamPerformanceStore(): SteamPerformanceStore | null {
  try {
    const globalStore = storeSingleton(
      (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore,
    );
    if (globalStore?.msgLimits) {
      recordResolvedStore("global");
      return globalStore;
    }

    const currentStore = resolveCurrentRuntimeStore();
    if (currentStore === null) return null;
    if (currentStore?.msgLimits) {
      recordResolvedStore("current_runtime");
      return currentStore;
    }

    const Store = findModuleExport(isStoreClass) as SteamPerformanceStoreClass | undefined;
    const snapshotStore = storeSingleton(Store);
    if (snapshotStore?.msgLimits) {
      recordResolvedStore("legacy_snapshot");
      return snapshotStore;
    }
    recordSteamPerformanceDiagnostic("store", {
      status: "unavailable",
      source: "none",
    });
    return null;
  } catch (error) {
    recordSteamPerformanceDiagnostic("store", {
      status: "resolution_failed",
      source: "unknown",
      error: steamPerformanceError(error),
    });
    return null;
  }
}

export function syncSteamPerformanceProfile(
  scope: "global" | "game",
  runningGameId: number | null,
  force = false,
): void {
  if (runningGameId === null) return;
  const store = resolveSteamPerformanceStore();
  const expectedGameId = String(runningGameId);
  if (!store) {
    recordSteamPerformanceDiagnostic("profile", {
      status: "store_unavailable",
      scope,
      running_game_id: expectedGameId,
    });
    return;
  }
  if (!store.SetGameSpecificProfileEnabled) {
    recordSteamPerformanceDiagnostic("profile", {
      status: "setter_unavailable",
      scope,
      running_game_id: expectedGameId,
    });
    return;
  }

  const {
    current_game_id: currentGameId,
    active_profile_game_id: activeProfileGameId,
  } = storeProfileIds(store);
  if (
    currentGameId !== null
    && currentGameId !== STEAM_GLOBAL_PROFILE_GAME_ID
    && appIdFromSteamGameId(currentGameId) !== expectedGameId
  ) {
    recordSteamPerformanceDiagnostic("profile", {
      status: "foreground_mismatch",
      scope,
      running_game_id: expectedGameId,
      current_game_id: currentGameId,
      active_profile_game_id: activeProfileGameId,
    });
    return;
  }

  const useGameProfile = scope === "game";
  const gameProfileActive = currentGameId !== null
    && currentGameId !== STEAM_GLOBAL_PROFILE_GAME_ID
    && activeProfileGameId === currentGameId;
  if (
    currentGameId !== null
    && activeProfileGameId !== null
    && gameProfileActive === useGameProfile
  ) {
    recordSteamPerformanceDiagnostic("profile", {
      status: "already_synced",
      scope,
      running_game_id: expectedGameId,
      current_game_id: currentGameId,
      active_profile_game_id: activeProfileGameId,
    });
    return;
  }

  if (currentGameId === null || activeProfileGameId === null) {
    const request = `${expectedGameId}:${useGameProfile}`;
    if (!force && legacyProfileRequests.get(store) === request) return;
    legacyProfileRequests.set(store, request);
  }

  try {
    store.SetGameSpecificProfileEnabled(useGameProfile);
    recordSteamPerformanceDiagnostic("profile", {
      status: "request_sent",
      scope,
      running_game_id: expectedGameId,
      current_game_id: currentGameId,
      active_profile_game_id: activeProfileGameId,
    });
  } catch (error) {
    legacyProfileRequests.delete(store);
    recordSteamPerformanceDiagnostic("profile", {
      status: "request_failed",
      scope,
      running_game_id: expectedGameId,
      current_game_id: currentGameId,
      active_profile_game_id: activeProfileGameId,
      error: steamPerformanceError(error),
    });
  }
}

export function subscribeSteamPerformanceState(
  onChange: () => void,
  client?: SteamPerformanceClient,
): () => void {
  let registration: SteamPerformanceRegistration | void;
  try {
    const resolvedClient = client ?? (
      typeof SteamClient === "undefined"
        ? {}
        : SteamClient as unknown as SteamPerformanceClient
    );
    const perf = resolvedClient.System?.Perf;
    const register = perf?.RegisterForStateChanges;
    if (typeof register !== "function") {
      recordSteamPerformanceDiagnostic("subscription", { status: "unavailable" });
      return () => {};
    }
    registration = register.call(perf, () => {
      void Promise.resolve().then(onChange);
    });
    recordSteamPerformanceDiagnostic("subscription", {
      status: "registered",
      cleanup_available: typeof registration?.unregister === "function",
    });
  } catch (error) {
    registration = undefined;
    recordSteamPerformanceDiagnostic("subscription", {
      status: "registration_failed",
      error: steamPerformanceError(error),
    });
  }
  return () => {
    try {
      registration?.unregister?.();
      if (registration && typeof registration.unregister === "function") {
        recordSteamPerformanceDiagnostic("subscription", { status: "unregistered" });
      }
    } catch (error) {
      // Steam registrations are best-effort and may already belong to an old CEF generation.
      recordSteamPerformanceDiagnostic("subscription", {
        status: "unregistration_failed",
        error: steamPerformanceError(error),
      });
    }
  };
}
