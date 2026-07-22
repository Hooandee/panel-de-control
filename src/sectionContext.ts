import { createContext, useContext, Provider } from "react";

/**
 * A section-scoped React context: one owner (the section) holds the shared
 * controller/state and provides it; the section's blocks consume it. Used where
 * blocks share cross-block state with writes/scope (Pantalla, Mandos, Potencia) —
 * as opposed to read-only monitors, which share a module singleton instead. The
 * consumer throws outside its provider so misuse fails loudly.
 */
export function createSectionContext<T>(name: string): readonly [Provider<T | null>, () => T] {
  const Ctx = createContext<T | null>(null);
  const use = (): T => {
    const c = useContext(Ctx);
    if (!c) throw new Error(`${name} outside its provider`);
    return c;
  };
  return [Ctx.Provider, use] as const;
}
