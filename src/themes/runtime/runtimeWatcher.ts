import type { CssLoaderSnapshot } from "../cssLoaderTypes";

interface ThemeRuntimeWatcherOptions {
  inspect(): Promise<CssLoaderSnapshot>;
  reconcile(snapshot: CssLoaderSnapshot): void;
  intervalMs?: number;
  setInterval?: (callback: () => void, intervalMs: number) => number;
  clearInterval?: (handle: number) => void;
  eventTarget?: Pick<EventTarget, "addEventListener" | "removeEventListener">;
  eventName?: string;
}

export const THEME_RUNTIME_CHANGED_EVENT = "pdc:themes-changed";

export interface ThemeRuntimeWatcher {
  refresh(): void;
  dispose(): void;
}

export function startThemeRuntimeWatcher({
  inspect,
  reconcile,
  intervalMs = 30_000,
  setInterval: schedule = window.setInterval.bind(window),
  clearInterval: cancel = window.clearInterval.bind(window),
  eventTarget,
  eventName = THEME_RUNTIME_CHANGED_EVENT,
}: ThemeRuntimeWatcherOptions): ThemeRuntimeWatcher {
  let disposed = false;
  let inspecting = false;
  let refreshPending = false;

  const refresh = () => {
    if (disposed) return;
    if (inspecting) {
      refreshPending = true;
      return;
    }
    inspecting = true;
    void inspect()
      .then((snapshot) => {
        if (!disposed) reconcile(snapshot);
      })
      .catch((error: unknown) => {
        if (disposed) return;
        reconcile({
          status: "error",
          themes: [],
          error: {
            code: "transport",
            message: error instanceof Error ? error.message : "Theme runtime inspection failed",
          },
        });
      })
      .finally(() => {
        inspecting = false;
        if (!disposed && refreshPending) {
          refreshPending = false;
          refresh();
        }
      });
  };

  refresh();
  const interval = schedule(refresh, intervalMs);
  const signals = eventTarget ?? (typeof window === "undefined" ? undefined : window);
  signals?.addEventListener(eventName, refresh);

  return {
    refresh,
    dispose() {
      if (disposed) return;
      disposed = true;
      cancel(interval);
      signals?.removeEventListener(eventName, refresh);
    },
  };
}
