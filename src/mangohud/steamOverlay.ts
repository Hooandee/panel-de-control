import { findModuleExport } from "@decky/ui";

export type SteamOverlayResolver = "global" | "module" | "unavailable";
export type SteamOverlayActivationOutcome =
  | "not_attempted"
  | "already_visible"
  | "confirmed"
  | "unavailable"
  | "exception"
  | "readback_timeout"
  | "readback_mismatch";

export interface SteamOverlayActivation {
  outcome: SteamOverlayActivationOutcome;
  before_level: number | null;
  requested_level: number | null;
  observed_level: number | null;
}

export interface SteamOverlayDiagnostics {
  snapshot_status: "available" | "unavailable";
  resolver: SteamOverlayResolver;
  settings_available: boolean;
  read_available: boolean;
  write_available: boolean;
  raw_level: number | null;
  ui_level: number | null;
  master_enabled: boolean | null;
  service_state: number | null;
  show_over_steam: boolean | null;
  last_activation: SteamOverlayActivation;
}

interface SteamPerfSettings {
  perf_overlay_level?: unknown;
  perf_overlay_service_state?: unknown;
  is_show_perf_overlay_over_steam_enabled?: unknown;
}

interface SteamPerfStore {
  msgSettingsGlobal?: SteamPerfSettings;
  SetPerfOverlayLevel?: (level: number) => unknown;
}

type WritableSteamPerfStore = SteamPerfStore & {
  SetPerfOverlayLevel: (level: number) => unknown;
};

interface ResolvedSteamPerfStore {
  store: SteamPerfStore;
  resolver: Exclude<SteamOverlayResolver, "unavailable">;
}

type StoreResolver = () => ResolvedSteamPerfStore | null;
type Wait = (milliseconds: number) => Promise<void>;

interface SteamWebpackRuntime {
  (moduleId: string): unknown;
  m?: Record<string, unknown>;
}

interface SteamWebpackChunks {
  push(chunk: [unknown[], Record<string, never>, (runtime: SteamWebpackRuntime) => void]): unknown;
}

const FULL_HUD_LEVEL = 1;
const READBACK_DELAY_MS = 100;
const DEFAULT_READBACK_ATTEMPTS = 10;

const NOT_ATTEMPTED: SteamOverlayActivation = {
  outcome: "not_attempted",
  before_level: null,
  requested_level: null,
  observed_level: null,
};

const levelOrNull = (value: unknown): number | null => (
  typeof value === "number"
  && Number.isInteger(value)
  && value >= 0
  && value <= 4
    ? value
    : null
);

const serviceStateOrNull = (value: unknown): number | null => (
  typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 2
    ? value
    : null
);

const uiLevel = (raw: number | null): number | null => {
  if (raw === null) return null;
  return ({ 0: 0, 4: 1, 1: 2, 2: 3, 3: 4 } as Record<number, number>)[raw] ?? null;
};

const asStore = (candidate: unknown): SteamPerfStore | null => {
  if ((typeof candidate !== "object" || candidate === null) && typeof candidate !== "function") {
    return null;
  }
  return candidate as SteamPerfStore;
};

const getStoreSingleton = (candidate: unknown): SteamPerfStore | null => {
  const direct = asStore(candidate);
  if (direct?.msgSettingsGlobal || typeof direct?.SetPerfOverlayLevel === "function") {
    return direct;
  }
  if (typeof candidate === "function") {
    const singleton = (candidate as unknown as { Get?: () => unknown }).Get?.();
    return asStore(singleton);
  }
  return null;
};

const hasSetter = (store: SteamPerfStore | null): store is WritableSteamPerfStore => (
  typeof store?.SetPerfOverlayLevel === "function"
);

const isUsableStore = (store: SteamPerfStore | null): store is SteamPerfStore => {
  const level = levelOrNull(store?.msgSettingsGlobal?.perf_overlay_level);
  return level !== null && (level !== 0 || hasSetter(store));
};

const isSteamPerfStoreClass = (candidate: unknown): boolean => (
  typeof candidate === "function"
  && typeof (candidate as { Get?: unknown }).Get === "function"
  && typeof (candidate as { prototype?: { SetPerfOverlayLevel?: unknown } })
    .prototype?.SetPerfOverlayLevel === "function"
);

const steamPerfStoreClassFromModule = (module: unknown): unknown => {
  const candidates: unknown[] = [module];
  if ((typeof module === "object" && module !== null) || typeof module === "function") {
    try {
      const exports = module as { default?: unknown } & Record<string, unknown>;
      candidates.push(exports.default, ...Object.values(exports));
    } catch {
      return null;
    }
  }
  return candidates.find(isSteamPerfStoreClass) ?? null;
};

let cachedRuntimeStore: {
  chunks: SteamWebpackChunks;
  store: SteamPerfStore;
} | null = null;

const resolveCurrentRuntimeSteamPerfStore = (): SteamPerfStore | null => {
  const chunks = (window as unknown as { webpackChunksteamui?: SteamWebpackChunks })
    .webpackChunksteamui;
  if (!chunks || typeof chunks.push !== "function") {
    cachedRuntimeStore = null;
    return null;
  }
  if (cachedRuntimeStore?.chunks === chunks && isUsableStore(cachedRuntimeStore.store)) {
    return cachedRuntimeStore.store;
  }
  cachedRuntimeStore = null;

  let runtime: SteamWebpackRuntime | null = null;
  try {
    chunks.push([
      [`pdc-steam-overlay-${Date.now()}`],
      {},
      (currentRuntime: SteamWebpackRuntime) => { runtime = currentRuntime; },
    ]);
  } catch {
    return null;
  }
  const currentRuntime = runtime as SteamWebpackRuntime | null;
  if (!currentRuntime?.m) return null;

  // Steam can load this store after Decky's module snapshot was created.
  for (const [moduleId, factory] of Object.entries(currentRuntime.m)) {
    let source = "";
    try {
      source = Function.prototype.toString.call(factory);
    } catch {
      continue;
    }
    if (
      !source.includes("SetShowPerfOverlayOverSteamEnabled")
      || !source.includes("CreateSettingsUpdateRequest")
    ) continue;

    try {
      const storeClass = steamPerfStoreClassFromModule(currentRuntime(moduleId));
      const store = getStoreSingleton(storeClass);
      if (store) {
        if (isUsableStore(store)) cachedRuntimeStore = { chunks, store };
        return store;
      }
    } catch {
      continue;
    }
  }
  return null;
};

const resolveSteamPerfStore: StoreResolver = () => {
  try {
    const globalStore = getStoreSingleton(
      (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore,
    );
    if (isUsableStore(globalStore)) {
      return { store: globalStore, resolver: "global" };
    }

    const currentRuntimeStore = resolveCurrentRuntimeSteamPerfStore();
    if (isUsableStore(currentRuntimeStore)) {
      return { store: currentRuntimeStore, resolver: "module" };
    }

    const storeClass = findModuleExport(isSteamPerfStoreClass);
    const moduleStore = getStoreSingleton(storeClass);
    if (isUsableStore(moduleStore)) {
      return { store: moduleStore, resolver: "module" };
    }

    if (hasSetter(globalStore)) return { store: globalStore, resolver: "global" };
    if (hasSetter(currentRuntimeStore)) {
      return { store: currentRuntimeStore, resolver: "module" };
    }
    if (hasSetter(moduleStore)) return { store: moduleStore, resolver: "module" };
    return globalStore ? { store: globalStore, resolver: "global" } : null;
  } catch {
    return null;
  }
};

const wait: Wait = (milliseconds) => new Promise((resolve) => {
  setTimeout(resolve, milliseconds);
});

export class SteamOverlayController {
  private lastActivation: SteamOverlayActivation = NOT_ATTEMPTED;
  private activationInFlight: Promise<SteamOverlayDiagnostics> | null = null;
  private activationGeneration = 0;

  constructor(
    private readonly resolveStore: StoreResolver = resolveSteamPerfStore,
    private readonly waitForReadback: Wait = wait,
    private readonly readbackAttempts = DEFAULT_READBACK_ATTEMPTS,
  ) {}

  diagnostics(): SteamOverlayDiagnostics {
    let resolved: ResolvedSteamPerfStore | null = null;
    try {
      resolved = this.resolveStore();
    } catch {
      resolved = null;
    }
    const settings = resolved?.store.msgSettingsGlobal;
    const rawLevel = levelOrNull(settings?.perf_overlay_level);
    const serviceState = serviceStateOrNull(settings?.perf_overlay_service_state);
    return {
      snapshot_status: rawLevel === null ? "unavailable" : "available",
      resolver: resolved?.resolver ?? "unavailable",
      settings_available: Boolean(settings),
      read_available: rawLevel !== null,
      write_available: typeof resolved?.store.SetPerfOverlayLevel === "function",
      raw_level: rawLevel,
      ui_level: uiLevel(rawLevel),
      master_enabled: rawLevel === null ? null : rawLevel !== 0,
      service_state: serviceState,
      show_over_steam: typeof settings?.is_show_perf_overlay_over_steam_enabled === "boolean"
        ? settings.is_show_perf_overlay_over_steam_enabled
        : null,
      last_activation: { ...this.lastActivation },
    };
  }

  ensureFullHudVisible(): Promise<SteamOverlayDiagnostics> {
    if (this.activationInFlight) return this.activationInFlight;
    const activation = this.activateFullHud(this.activationGeneration);
    this.activationInFlight = activation;
    const clear = () => {
      if (this.activationInFlight === activation) this.activationInFlight = null;
    };
    void activation.then(clear, clear);
    return activation;
  }

  cancelActivation(): void {
    this.activationGeneration += 1;
    this.activationInFlight = null;
  }

  private finishActivation(
    outcome: SteamOverlayActivationOutcome,
    beforeLevel: number | null,
    requestedLevel: number | null,
    observedLevel: number | null,
  ): SteamOverlayDiagnostics {
    this.lastActivation = {
      outcome,
      before_level: beforeLevel,
      requested_level: requestedLevel,
      observed_level: observedLevel,
    };
    return this.diagnostics();
  }

  private async activateFullHud(generation: number): Promise<SteamOverlayDiagnostics> {
    let before = this.diagnostics();
    for (
      let attempt = 0;
      before.raw_level === null && attempt < this.readbackAttempts;
      attempt += 1
    ) {
      await this.waitForReadback(READBACK_DELAY_MS);
      before = this.diagnostics();
    }
    if (generation !== this.activationGeneration) return this.diagnostics();
    if (before.raw_level === null) {
      return this.finishActivation("unavailable", null, null, null);
    }
    if (before.raw_level !== 0) {
      return this.finishActivation(
        "already_visible",
        before.raw_level,
        null,
        before.raw_level,
      );
    }

    const resolved = this.resolveStore();
    const store = resolved?.store;
    const setter = store?.SetPerfOverlayLevel;
    if (!store || typeof setter !== "function") {
      return this.finishActivation("unavailable", 0, FULL_HUD_LEVEL, 0);
    }

    try {
      setter.call(store, FULL_HUD_LEVEL);
    } catch {
      return this.finishActivation(
        "exception",
        0,
        FULL_HUD_LEVEL,
        this.diagnostics().raw_level,
      );
    }

    let observed = this.diagnostics().raw_level;
    for (let attempt = 0; attempt < this.readbackAttempts && observed === 0; attempt += 1) {
      await this.waitForReadback(READBACK_DELAY_MS);
      observed = this.diagnostics().raw_level;
    }
    const outcome = observed === FULL_HUD_LEVEL
      ? "confirmed"
      : observed === 0
        ? "readback_timeout"
        : "readback_mismatch";
    return this.finishActivation(outcome, 0, FULL_HUD_LEVEL, observed);
  }
}

export const steamOverlay = new SteamOverlayController();
