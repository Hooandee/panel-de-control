import type { ThemeStorageBackend } from "../themes/runtime/themeStorage";

/**
 * Theme storage on Windows. The companion only reaches Steam through CDP evaluations, so the host keeps an
 * outbox: every 2 s cycle the companion takes the pending writes, persists them (fsync) and settles them,
 * and on the first cycle it hands over what is already on disk. Until that seed arrives a read waits; if it
 * never comes the read fails instead of answering "nothing saved".
 */
export interface WindowsStorageWrite {
  seq: number;
  catalogId: string;
  key: string;
  value: string;
}

export interface WindowsStorageSettlement {
  /** What is on disk, by theme; sent while `status().seeded` is false. */
  seed?: Record<string, Record<string, string>>;
  /** Themes whose file the companion could not read: their reads fail rather than look empty. */
  unreadable?: readonly string[];
  results?: readonly { seq: number; ok: boolean }[];
}

export interface WindowsStorageStatus {
  seeded: boolean;
  pending: number;
}

export interface WindowsThemeStorage {
  backend: ThemeStorageBackend;
  status(): WindowsStorageStatus;
  take(): WindowsStorageWrite[];
  settle(settlement: WindowsStorageSettlement): WindowsStorageStatus;
  dispose(): void;
}

export const STORAGE_SEED_TIMEOUT_MS = 15_000;
export const STORAGE_WRITE_TIMEOUT_MS = 20_000;

interface PendingWrite extends WindowsStorageWrite {
  done(ok: boolean): void;
}

function stringRecord(value: unknown): Map<string, string> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const entries = Object.entries(value).filter((entry): entry is [string, string] => typeof entry[1] === "string");
  return new Map(entries);
}

export function createWindowsThemeStorage(
  timers: Pick<typeof globalThis, "setTimeout" | "clearTimeout"> = globalThis,
): WindowsThemeStorage {
  let seed: Map<string, Map<string, string>> | null = null;
  let unreadable = new Set<string>();
  let nextSeq = 1;
  let disposed = false;
  const writes: PendingWrite[] = [];
  const seedWaiters = new Set<(ready: boolean) => void>();

  const waitForSeed = (): Promise<boolean> => {
    if (seed) return Promise.resolve(true);
    if (disposed) return Promise.resolve(false);
    return new Promise((resolve) => {
      const finish = (ready: boolean) => {
        timers.clearTimeout(timer);
        seedWaiters.delete(finish);
        resolve(ready);
      };
      const timer = timers.setTimeout(() => finish(false), STORAGE_SEED_TIMEOUT_MS);
      seedWaiters.add(finish);
    });
  };

  const backend: ThemeStorageBackend = {
    async get(catalogId, key) {
      if (!await waitForSeed() || !seed) return { ok: false, code: "unavailable" };
      for (let index = writes.length - 1; index >= 0; index -= 1) {
        const write = writes[index];
        if (write.catalogId === catalogId && write.key === key) return { ok: true, value: write.value };
      }
      if (unreadable.has(catalogId)) return { ok: false, code: "read_failed" };
      return { ok: true, value: seed.get(catalogId)?.get(key) ?? null };
    },
    set(catalogId, key, value) {
      if (disposed) return Promise.resolve({ ok: false, code: "unavailable" });
      return new Promise((resolve) => {
        const seq = nextSeq;
        nextSeq += 1;
        const timer = timers.setTimeout(() => write.done(false), STORAGE_WRITE_TIMEOUT_MS);
        const write: PendingWrite = {
          seq,
          catalogId,
          key,
          value,
          done(ok) {
            timers.clearTimeout(timer);
            const index = writes.indexOf(write);
            if (index >= 0) writes.splice(index, 1);
            resolve(ok ? { ok: true } : { ok: false, code: "write_failed" });
          },
        };
        writes.push(write);
      });
    },
  };

  const status = (): WindowsStorageStatus => ({ seeded: seed !== null, pending: writes.length });

  return {
    backend,
    status,
    take: () => writes.map(({ seq, catalogId, key, value }) => ({ seq, catalogId, key, value })),
    settle(settlement) {
      if (settlement.seed && !seed) {
        seed = new Map(Object.entries(settlement.seed).flatMap(([catalogId, values]) => {
          const parsed = stringRecord(values);
          return parsed ? [[catalogId, parsed] as const] : [];
        }));
        unreadable = new Set((settlement.unreadable ?? []).filter((id) => typeof id === "string"));
        for (const finish of [...seedWaiters]) finish(true);
      }
      for (const result of settlement.results ?? []) {
        const write = writes.find((candidate) => candidate.seq === result.seq);
        if (!write) continue;
        if (result.ok === true && seed) {
          const values = seed.get(write.catalogId) ?? new Map<string, string>();
          values.set(write.key, write.value);
          seed.set(write.catalogId, values);
          unreadable.delete(write.catalogId);
        }
        write.done(result.ok === true);
      }
      return status();
    },
    dispose() {
      disposed = true;
      for (const finish of [...seedWaiters]) finish(false);
      for (const write of [...writes]) write.done(false);
    },
  };
}
