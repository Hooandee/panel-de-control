import { routerHook } from "@decky/api";

const Nothing = () => null;

/**
 * Decky re-renders global components only when their count changes, so a reload (old removed,
 * new added) would keep rendering the previous bundle's component. A throwaway entry added and
 * removed right after forces it to pick up the current one.
 */
export function registerGlobal(name: string, component: Parameters<typeof routerHook.addGlobalComponent>[1]): () => void {
  const nudge = `${name}:refresh`;
  try {
    routerHook.addGlobalComponent(name, component);
    routerHook.addGlobalComponent(nudge, Nothing);
    setTimeout(() => {
      try {
        routerHook.removeGlobalComponent(nudge);
      } catch {
        /* router gone */
      }
    }, 0);
  } catch {
    return () => undefined;
  }
  return () => {
    try {
      routerHook.removeGlobalComponent(name);
    } catch {
      /* router already gone */
    }
  };
}
