import { currentSteamRuntime, resolveSteamPerformanceStore } from "./performanceRuntime";
import { readRunningGame } from "../tdp/runningGame";
import type { PerformanceSettingsDeps } from "./performanceSettings";

interface QueryClientView {
  getQueryData: (key: string[]) => unknown;
  fetchQuery?: (options: { queryKey: string[]; queryFn: () => Promise<unknown>; retry: false }) => Promise<unknown>;
}
interface DisplayView {
  is_primary?: boolean;
  is_enabled?: boolean;
  is_internal?: boolean;
  is_vrr_capable?: boolean;
  supported_refresh_rates?: number[];
}
interface SettingsView {
  GetClientSetting: (name: string) => [unknown, (value: number | boolean) => unknown];
}
interface ClientState {
  runtime: unknown;
  client: QueryClientView;
  pending: Set<string>;
  retryAfter: Map<string, number>;
}
let cachedClient: ClientState | null = null;
const RETRY_MS = 5000;
const TIMEOUT_MS = 4000;

function exportsMatching(tokens: string[]): unknown[] {
  const runtime = currentSteamRuntime();
  if (!runtime?.m) return [];
  const values: unknown[] = [];
  for (const [id, factory] of Object.entries(runtime.m)) {
    try {
      if (typeof factory !== "function" || !tokens.every((token) => String(factory).includes(token))) continue;
      const exported = runtime(id);
      if (exported && typeof exported === "object") values.push(...Object.values(exported));
    } catch { continue; }
  }
  return values;
}

interface StateService {
  GetState: (request: Record<string, never>) => Promise<{
    BSuccess: () => boolean;
    Body: () => { toObject: () => { state?: unknown } };
  }>;
}

function loadState(key: string[]): (() => Promise<unknown>) | null {
  if (key[0] === "CSystemDisplayManagerStore") {
    type DisplayStoreClass = { Get: () => { GetState: () => Promise<unknown> }; prototype: { GetState?: unknown } };
    const candidates = new Set(exportsMatching(["CSystemDisplayManagerStore", "Failed to fetch display manager state"])
      .filter((value): value is DisplayStoreClass => typeof value === "function"
        && typeof (value as unknown as DisplayStoreClass).Get === "function"
        && typeof (value as unknown as DisplayStoreClass).prototype?.GetState === "function"));
    if (candidates.size !== 1) return null;
    const [storeClass] = candidates;
    return () => storeClass.Get().GetState();
  }
  const signature = key[0] === "GamescopeService" ? "Gamescope.GetState#1"
    : key[0] === "SteamOSService" ? "SteamOSManager.GetState#1" : null;
  if (!signature) return null;
  const candidates = new Set(exportsMatching([signature]).filter((value): value is StateService => {
    if (!value || typeof value !== "object") return false;
    const getState = (value as StateService).GetState;
    return typeof getState === "function" && String(getState).includes(signature);
  }));
  if (candidates.size !== 1) return null;
  const [service] = candidates;
  return async () => {
    const response = await service.GetState({});
    if (response.BSuccess() !== true) throw new Error("Steam capability request failed");
    const state = response.Body().toObject().state;
    if (!state || typeof state !== "object") throw new Error("Steam capability state unavailable");
    return state;
  };
}

function boundedRead(load: () => Promise<unknown>): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Steam capability request timed out")), TIMEOUT_MS);
    Promise.resolve().then(load).then((value) => {
      clearTimeout(timer);
      if (!value || typeof value !== "object") reject(new Error("Steam capability state unavailable"));
      else resolve(value);
    }, (error) => { clearTimeout(timer); reject(error); });
  });
}

function hydrate(client: QueryClientView, key: string[]): void {
  const state = cachedClient;
  if (!state || state.client !== client || !client.fetchQuery) return;
  const id = key.join("/");
  if (state.pending.has(id) || Date.now() < (state.retryAfter.get(id) ?? 0)) return;
  state.retryAfter.set(id, Date.now() + RETRY_MS);
  const load = loadState(key);
  if (!load) return;
  state.pending.add(id);
  void Promise.resolve().then(() => client.fetchQuery!({ queryKey: key, queryFn: () => boundedRead(load), retry: false }))
    .catch(() => { state.retryAfter.set(id, Date.now() + RETRY_MS); })
    .finally(() => { state.pending.delete(id); });
}

function queryClient(): QueryClientView | null {
  const runtime = currentSteamRuntime();
  if (!runtime?.m) return null;
  if (cachedClient?.runtime === runtime) return cachedClient.client;
  const candidates = new Set<QueryClientView>();
  for (const value of exportsMatching(["ReactQueryDevtools", "offlineFirst"])) {
    if (value && typeof value === "object" && typeof (value as QueryClientView).getQueryData === "function") {
      candidates.add(value as QueryClientView);
    }
  }
  if (candidates.size !== 1) return null;
  const [client] = candidates;
  cachedClient = { runtime, client, pending: new Set(), retryAfter: new Map() };
  return client;
}

function readQuery<T>(key: string[]): T | null {
  try {
    const client = queryClient();
    if (!client) return null;
    const value = client.getQueryData(key) as T | undefined;
    if (value == null) hydrate(client, key);
    return value ?? null;
  }
  catch { return null; }
}

function settingsStore(): SettingsView | null {
  const store = (window as unknown as { settingsStore?: SettingsView }).settingsStore;
  return typeof store?.GetClientSetting === "function" ? store : null;
}

export function createPerformanceSettingsDeps(): PerformanceSettingsDeps {
  return {
    store: () => resolveSteamPerformanceStore(),
    runningGameId: () => readRunningGame()?.liveAppid ?? null,
    settings: {
      get: (name) => settingsStore()?.GetClientSetting(name)[0],
      set: (name, value) => {
        const store = settingsStore();
        if (!store) throw new Error("Steam settings unavailable");
        return store.GetClientSetting(name)[1](value);
      },
    },
    display: () => {
      const state = readQuery<{ displays?: DisplayView[] }>(["CSystemDisplayManagerStore", "State"]);
      const display = state?.displays?.find((item) => item.is_primary === true)
        ?? state?.displays?.find((item) => item.is_enabled === true);
      if (typeof display?.is_internal !== "boolean") return null;
      return {
        external: !display.is_internal,
        isVrrCapable: display.is_vrr_capable,
        supportedRefreshRates: display.supported_refresh_rates,
      };
    },
    gamescope: () => readQuery(["GamescopeService", "State"]),
    steamOs: () => readQuery(["SteamOSService", "State", "Manager"]),
  };
}
