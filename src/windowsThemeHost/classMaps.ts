// Decky publishes Steam's CSS module maps ({ Name: "hash" }) as DFL.classMap and themes build their selectors from
// them. Windows has no Decky: without this, every theme falls back to the hashes it was written with, and a client
// build that renamed one leaves the selector matching nothing (Duo's leaving game page stayed visible).
export const HOST_CLASS_MAPS_KEY = "__pdcHostClassMaps";

type WebpackRequire = ((id: string) => unknown) & { m: Record<string, unknown> };
type ClassMapScope = typeof globalThis & { webpackChunksteamui?: { push(chunk: unknown[]): unknown } };

export function isClassMap(value: unknown): value is Readonly<Record<string, string>> {
  if (!value || typeof value !== "object" || Array.isArray(value) || (value as { __esModule?: unknown }).__esModule) return false;
  const values = Object.values(value);
  return values.length > 0 && values.every((entry) => typeof entry === "string");
}

export function collectClassMaps(scope: typeof globalThis): readonly Readonly<Record<string, string>>[] {
  let require: WebpackRequire | undefined;
  try {
    (scope as ClassMapScope).webpackChunksteamui?.push([[Symbol("pdc-class-maps")], {}, (found: WebpackRequire) => { require = found; }]);
  } catch {
    return [];
  }
  if (!require) return [];
  const maps: Readonly<Record<string, string>>[] = [];
  for (const id of Object.keys(require.m)) {
    let exported: unknown;
    try {
      exported = require(id);
    } catch {
      continue;
    }
    if (isClassMap(exported)) maps.push(exported);
  }
  return maps;
}

/** Built on first read; an empty result is not kept, so a read before Steam's bundles load tries again. */
export function installHostClassMaps(scope: typeof globalThis): () => void {
  let maps: readonly Readonly<Record<string, string>>[] | undefined;
  Object.defineProperty(scope, HOST_CLASS_MAPS_KEY, {
    configurable: true,
    enumerable: false,
    get: () => {
      if (!maps?.length) maps = Object.freeze(collectClassMaps(scope));
      return maps;
    },
  });
  return () => {
    delete (scope as unknown as Record<string, unknown>)[HOST_CLASS_MAPS_KEY];
  };
}
