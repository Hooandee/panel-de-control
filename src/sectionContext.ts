import { createContext, useContext, Provider } from "react";

export function createSectionContext<T>(name: string): readonly [Provider<T | null>, () => T] {
  const Ctx = createContext<T | null>(null);
  const use = (): T => {
    const c = useContext(Ctx);
    if (!c) throw new Error(`${name} outside its provider`);
    return c;
  };
  return [Ctx.Provider, use] as const;
}
