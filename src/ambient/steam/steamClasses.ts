import { findModule } from "@decky/ui";

const cache = new Map<string, string | null>();

/** Resolves a Steam CSS module key (e.g. "BasicHome") to its hashed class; hashes change per Steam build. */
export function steamClass(key: string): string | null {
  if (cache.has(key)) return cache.get(key) ?? null;
  let value: string | null = null;
  try {
    const mod = findModule((m: unknown) => !!m && typeof m === "object" && typeof (m as Record<string, unknown>)[key] === "string");
    value = mod ? (mod as Record<string, string>)[key] : null;
  } catch {
    value = null;
  }
  if (value) cache.set(key, value);
  return value;
}

export function clearSteamClassCache(): void {
  cache.clear();
}
