/**
 * Durable per-theme storage. CEF's localStorage does not reliably survive a reboot, so a runtime keeps what
 * the user arranged (dock, groups, library order) here and the backend writes it through fsync.
 *
 * `get` resolves null only when the key was never stored; a backend that cannot answer rejects, so a
 * runtime never mistakes a failed read for "nothing saved" and overwrites the user's layout with defaults.
 * `set` resolves true once the value is on disk, false when it was rejected (size, key) or failed.
 */
export interface ThemeExtensionStorageAccess {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<boolean>;
}

/** What a platform provides; every call names the theme the host scoped it to. */
export interface ThemeStorageBackend {
  get(catalogId: string, key: string): Promise<unknown>;
  set(catalogId: string, key: string, value: string): Promise<unknown>;
}

export interface ThemeStorageProvider {
  forTheme(catalogId: string): Readonly<ThemeExtensionStorageAccess>;
}

export const THEME_STORAGE_MAX_VALUE_BYTES = 128 * 1024;
export const THEME_STORAGE_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export class ThemeStorageError extends Error {
  constructor(readonly code: string) {
    super(`Theme storage ${code}`);
    this.name = "ThemeStorageError";
  }
}

export function themeStorageValueFits(value: string): boolean {
  return value.length <= THEME_STORAGE_MAX_VALUE_BYTES
    && new TextEncoder().encode(value).byteLength <= THEME_STORAGE_MAX_VALUE_BYTES;
}

function reply(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new ThemeStorageError("invalid_reply");
  return value as Record<string, unknown>;
}

function failureCode(value: Record<string, unknown>, fallback: string): string {
  return typeof value.code === "string" && /^[a-z_]{1,40}$/.test(value.code) ? value.code : fallback;
}

export function createThemeStorage(backend: ThemeStorageBackend): ThemeStorageProvider {
  // One queue per theme: a read issued after a write sees it, and two writes land in the order made.
  const queues = new Map<string, Promise<unknown>>();
  const enqueue = <T>(catalogId: string, run: () => Promise<T>): Promise<T> => {
    const previous = queues.get(catalogId) ?? Promise.resolve();
    const next = previous.then(run, run);
    const settled = next.catch(() => undefined);
    queues.set(catalogId, settled);
    void settled.then(() => {
      if (queues.get(catalogId) === settled) queues.delete(catalogId);
    });
    return next;
  };

  return {
    forTheme(catalogId) {
      return Object.freeze({
        get(key: string) {
          if (typeof key !== "string" || !THEME_STORAGE_KEY.test(key)) {
            return Promise.reject(new ThemeStorageError("invalid_key"));
          }
          return enqueue(catalogId, async () => {
            const result = reply(await backend.get(catalogId, key));
            if (result.ok !== true) throw new ThemeStorageError(failureCode(result, "read_failed"));
            if (result.value === null || result.value === undefined) return null;
            if (typeof result.value !== "string") throw new ThemeStorageError("invalid_reply");
            return result.value;
          });
        },
        set(key: string, value: string) {
          if (
            typeof key !== "string"
            || !THEME_STORAGE_KEY.test(key)
            || typeof value !== "string"
            || value.includes("\0")
            || !themeStorageValueFits(value)
          ) return Promise.resolve(false);
          return enqueue(catalogId, async () => {
            try {
              return reply(await backend.set(catalogId, key, value)).ok === true;
            } catch {
              return false;
            }
          });
        },
      });
    },
  };
}
