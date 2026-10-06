export interface ThemeDataRecord {
  summary: string;
  value: unknown;
  updatedAt: number;
  bytes: number;
}

export interface ThemeDataEntry {
  catalogId: string;
  summary: string;
  updatedAt: number;
  bytes: number;
}

export type ThemeDataSaveResult = "saved" | "rejected" | "failed";

export interface ThemeDataRpcHost {
  get(catalogId: string): Promise<unknown>;
  save(catalogId: string, summary: string, value: unknown): Promise<unknown>;
  list(): Promise<unknown>;
  reset(catalogId: string): Promise<unknown>;
}

// What a mounted theme runtime sees: only its own data, bound to its catalog identity by the host.
export interface ThemeDataAccess {
  read(): Promise<ThemeDataRecord | null>;
  write(record: { summary: string; value: unknown }): Promise<ThemeDataSaveResult>;
  subscribe(listener: (record: ThemeDataRecord | null) => void): () => void;
}

export interface ThemeDataBridge {
  forTheme(catalogId: string): ThemeDataAccess;
}

const SAFE_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MAX_SUMMARY_CHARS = 120;

let configuredHost: ThemeDataRpcHost | undefined;
let configuredLease: symbol | null = null;
const listeners = new Map<string, Set<(record: ThemeDataRecord | null) => void>>();

export function configureThemeDataRpcHost(host: ThemeDataRpcHost): () => void {
  const lease = Symbol("theme-data-rpc-host");
  configuredHost = host;
  configuredLease = lease;
  return () => {
    if (configuredLease !== lease) return;
    configuredHost = undefined;
    configuredLease = null;
  };
}

function requireHost(host?: ThemeDataRpcHost): ThemeDataRpcHost {
  const active = host ?? configuredHost;
  if (!active) throw new Error("Theme data backend is unavailable");
  return active;
}

const isCount = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0;

export function parseThemeDataRecord(value: unknown): ThemeDataRecord | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const input = value as Record<string, unknown>;
  if (typeof input.summary !== "string" || !("value" in input) || !isCount(input.updatedAt) || !isCount(input.bytes)) {
    return null;
  }
  return { summary: input.summary, value: input.value, updatedAt: input.updatedAt, bytes: input.bytes };
}

export function parseThemeDataEntries(value: unknown): ThemeDataEntry[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item): ThemeDataEntry[] => {
    if (typeof item !== "object" || item === null) return [];
    const input = item as Record<string, unknown>;
    if (
      typeof input.catalogId !== "string" || !SAFE_ID.test(input.catalogId)
      || typeof input.summary !== "string" || !isCount(input.updatedAt) || !isCount(input.bytes)
    ) return [];
    return [{ catalogId: input.catalogId, summary: input.summary, updatedAt: input.updatedAt, bytes: input.bytes }];
  });
}

function notify(catalogId: string, record: ThemeDataRecord | null): void {
  for (const listener of [...(listeners.get(catalogId) ?? [])]) {
    try {
      listener(record);
    } catch {
      // One theme's listener failing must not stop the others from hearing the change.
    }
  }
}

export async function listThemeData(host?: ThemeDataRpcHost): Promise<ThemeDataEntry[]> {
  return parseThemeDataEntries(await requireHost(host).list());
}

export async function resetThemeData(catalogId: string, host?: ThemeDataRpcHost): Promise<boolean> {
  if (!SAFE_ID.test(catalogId)) return false;
  const result = await requireHost(host).reset(catalogId) as { ok?: unknown } | null;
  if (result?.ok !== true) return false;
  notify(catalogId, null);
  return true;
}

export function createThemeDataBridge(host?: ThemeDataRpcHost): ThemeDataBridge {
  return {
    forTheme(catalogId) {
      if (!SAFE_ID.test(catalogId)) throw new Error("Theme data identity is invalid");
      return Object.freeze({
        async read() {
          return parseThemeDataRecord(await requireHost(host).get(catalogId));
        },
        async write(record: { summary: string; value: unknown }): Promise<ThemeDataSaveResult> {
          if (typeof record?.summary !== "string" || record.summary.length > MAX_SUMMARY_CHARS) return "rejected";
          try {
            const result = await requireHost(host).save(catalogId, record.summary, record.value) as
              { ok?: unknown; record?: unknown } | null;
            if (result?.ok !== true) return "rejected";
            return "saved";
          } catch {
            return "failed";
          }
        },
        subscribe(listener: (next: ThemeDataRecord | null) => void) {
          const set = listeners.get(catalogId) ?? new Set();
          set.add(listener);
          listeners.set(catalogId, set);
          return () => {
            set.delete(listener);
            if (set.size === 0) listeners.delete(catalogId);
          };
        },
      });
    },
  };
}
