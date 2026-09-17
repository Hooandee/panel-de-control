import { findModuleByExport, findModuleExport } from "@decky/ui";

import {
  selectSteamPerformanceComponents,
  SteamPerformanceComponents,
  SteamPerformanceStoreView,
} from "./performanceSurface";

interface SteamPerformanceStore extends SteamPerformanceStoreView {
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
  } catch {
    return null;
  }
  const resolved = runtime as SteamWebpackRuntime | null;
  if (!resolved?.m) return null;
  cachedRuntime = { chunks, runtime: resolved };
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
  if (candidates.length !== 1) return {};
  const [components] = candidates;
  if (cachedRuntime?.runtime === runtime) cachedRuntime.components = components;
  return components;
};

export function discoverSteamPerformanceComponents(): SteamPerformanceComponents {
  let snapshot: SteamPerformanceComponents = {};
  try {
    const module = findModuleByExport(isResetExport);
    snapshot = componentsFromModule(module);
  } catch {
    snapshot = {};
  }
  const current = discoverCurrentRuntimeComponents();
  return current ?? snapshot;
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
    && typeof type.prototype?.SetVRREnabled === "function"
    && typeof type.prototype?.SetSplitScalingScaler === "function"
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
      "SetVRREnabled",
      "SetSplitScalingScaler",
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
  if (candidates.size > 1) return null;
  const [store] = candidates;
  if (cachedRuntime?.runtime === runtime) cachedRuntime.store = store;
  return store;
};

export function resolveSteamPerformanceStore(): SteamPerformanceStore | null {
  try {
    const globalStore = storeSingleton(
      (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore,
    );
    if (globalStore?.msgLimits) return globalStore;

    const currentStore = resolveCurrentRuntimeStore();
    if (currentStore === null) return null;
    if (currentStore?.msgLimits) return currentStore;

    const Store = findModuleExport(isStoreClass) as SteamPerformanceStoreClass | undefined;
    const snapshotStore = storeSingleton(Store);
    return snapshotStore?.msgLimits ? snapshotStore : null;
  } catch {
    return null;
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
    registration = resolvedClient.System?.Perf?.RegisterForStateChanges?.(() => {
      void Promise.resolve().then(onChange);
    });
  } catch {
    registration = undefined;
  }
  return () => {
    try {
      registration?.unregister?.();
    } catch {
      // Steam registrations are best-effort and may already belong to an old CEF generation.
    }
  };
}
