import { Router } from "@decky/ui";

export type Surface = "home" | "library" | "other";

interface HistoryLike {
  location?: { pathname?: string };
  listen?: (cb: (location: { pathname?: string }) => void) => () => void;
}

function history(): HistoryLike | undefined {
  try {
    return (Router as unknown as { WindowStore?: { GamepadUIMainWindowInstance?: { m_history?: HistoryLike } } })
      .WindowStore?.GamepadUIMainWindowInstance?.m_history;
  } catch {
    return undefined;
  }
}

export function surfaceForPath(pathname: string | undefined): Surface {
  if (!pathname) return "other";
  if (pathname === "/library/home" || pathname === "/library" || pathname === "/") return pathname === "/library" ? "library" : "home";
  if (pathname.startsWith("/library/app/")) return "other";
  if (pathname.startsWith("/library/")) return "library";
  return "other";
}

export function currentSurface(): Surface {
  return surfaceForPath(history()?.location?.pathname);
}

/** Big Picture route changes; falls back to a slow poll when the router history is unavailable. */
export function subscribeSurface(listener: (surface: Surface) => void): () => void {
  let last = currentSurface();
  const emit = (surface: Surface) => {
    if (surface === last) return;
    last = surface;
    listener(surface);
  };
  let unlisten: (() => void) | undefined;
  try {
    unlisten = history()?.listen?.((location) => emit(surfaceForPath(location?.pathname)));
  } catch {
    unlisten = undefined;
  }
  const poll = setInterval(() => emit(currentSurface()), unlisten ? 10000 : 1500);
  return () => {
    clearInterval(poll);
    try {
      unlisten?.();
    } catch {
      /* router gone */
    }
  };
}
