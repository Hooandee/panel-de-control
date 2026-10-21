// On Windows a running game gets Steam's in-game overlay: the Steam button opens that overlay's own menu instead of
// Big Picture, which is where the theme lives. While a theme runtime is mounted the button goes back to Big Picture's
// Home over the game, as on a console, and resuming the game raises its window again. However Big Picture comes back
// over a running game (Game Bar, Alt+Tab), Steam keeps the controller on the game until the game's overlay state says
// Steam's UI is in front: that state is set whenever Big Picture has focus outside the running game's page.

/** Steam's composition modes (`SetOverlayState`): with the game's overlay state above Hidden, Steam gives the
 * controller to its own UI (focused appid 769); Hidden gives it back to the game. */
const COMPOSITION_HIDDEN = 0;
const COMPOSITION_OVERLAY = 2;
/** The overlay takes the navigation context when it activates; Big Picture's is taken back after it. */
const REACTIVATE_DELAYS_MS = [0, 120, 400];
/** A game asking for its overlay (store page, purchase) is followed within this window by the activation. */
const GAME_REQUEST_WINDOW_MS = 1_500;
const OVERLAY_POLL_MS = 1_000;
/** Steam's own UI in its focus events and composition queue. */
const STEAM_UI_APPID = 769;

interface Unregistrable {
  unregister?(): void;
}

interface SteamHistory {
  location?: { pathname?: string };
  listen?(listener: (location: { pathname?: string }) => void): () => void;
}

interface NavigationContext {
  SetActive?(active: boolean, window?: unknown): void;
}

interface SteamWindowInstance {
  OnHomeButtonPressed?(...args: unknown[]): unknown;
  m_CompositionStateStore?: { GetCurrentlyFocusedAppidSubscribableValue?(): { Value?: unknown } };
  GetFocusNavContext?(): NavigationContext | undefined;
  MainRunningAppID?: number;
  Navigator?: { Home?(): void };
  BrowserWindow?: (Pick<Window, "addEventListener" | "removeEventListener"> & {
    document?: Pick<Document, "hasFocus">;
    SteamClient?: { Window?: { BringToFront?(): void } };
  }) | null;
  m_history?: SteamHistory;
}

interface SteamButtonScope {
  SteamClient?: {
    Overlay?: {
      RegisterForOverlayActivated?(callback: (pid: number, appId: number, active: boolean, user: boolean) => void): Unregistrable | undefined;
      RegisterForActivateOverlayRequests?(callback: (...args: unknown[]) => void): Unregistrable | undefined;
      SetOverlayState?(gameId: string, mode: number): void;
    };
    Apps?: { RaiseWindowForGame?(gameId: string): unknown };
  };
  SteamUIStore?: {
    RunningApps?: readonly { appid?: number; m_gameid?: string; gameid?: string }[];
    WindowStore?: {
      GamepadUIMainWindowInstance?: SteamWindowInstance;
      m_mapOverlayPopupByPID?: { values?(): Iterable<SteamWindowInstance> };
    };
  };
  appStore?: { GetAppOverviewByAppID?(appId: number): { m_gameid?: string; gameid?: string } | undefined };
}

/** Records a failure code; it reaches the companion as one of the host's errors. */
export type SteamButtonLog = (code: string) => void;

function gameIdFor(steam: SteamButtonScope, appId: number | undefined): string | null {
  if (!appId) return null;
  const running = steam.SteamUIStore?.RunningApps?.find((app) => app.appid === appId);
  const overview = steam.appStore?.GetAppOverviewByAppID?.(appId);
  const id = running?.m_gameid ?? running?.gameid ?? overview?.m_gameid ?? overview?.gameid ?? String(appId);
  return id && id !== "0" ? id : null;
}

export function installSteamButtonHome(
  scope: typeof globalThis,
  isActive: () => boolean,
  log: SteamButtonLog,
  timers: Pick<typeof globalThis, "setInterval" | "clearInterval" | "setTimeout"> = globalThis,
): () => void {
  const steam = scope as unknown as SteamButtonScope;
  const main = () => steam.SteamUIStore?.WindowStore?.GamepadUIMainWindowInstance;
  let lastGameRequest = -Infinity;

  const activateBigPicture = () => {
    const window = main();
    try {
      window?.GetFocusNavContext?.()?.SetActive?.(true, window.BrowserWindow);
    } catch {
      log("steam_button_focus_failed");
    }
  };

  const showBigPictureHome = (appId: number | undefined) => {
    const gameId = gameIdFor(steam, appId);
    try {
      if (gameId) steam.SteamClient?.Overlay?.SetOverlayState?.(gameId, COMPOSITION_OVERLAY);
      const window = main();
      window?.Navigator?.Home?.();
      window?.BrowserWindow?.SteamClient?.Window?.BringToFront?.();
    } catch {
      log("steam_button_home_failed");
    }
    for (const delay of REACTIVATE_DELAYS_MS) timers.setTimeout(activateBigPicture, delay);
  };

  const patched = new Map<SteamWindowInstance, unknown>();
  const patchOverlays = () => {
    for (const overlay of steam.SteamUIStore?.WindowStore?.m_mapOverlayPopupByPID?.values?.() ?? []) {
      if (patched.has(overlay)) continue;
      const own = Object.prototype.hasOwnProperty.call(overlay, "OnHomeButtonPressed") ? overlay.OnHomeButtonPressed : undefined;
      const original = overlay.OnHomeButtonPressed;
      if (typeof original !== "function") continue;
      patched.set(overlay, own);
      overlay.OnHomeButtonPressed = function (this: SteamWindowInstance, ...args: unknown[]) {
        if (!isActive()) return original.apply(this, args);
        showBigPictureHome(this.MainRunningAppID);
        return undefined;
      };
    }
  };
  patchOverlays();
  const overlayPoll = timers.setInterval(patchOverlays, OVERLAY_POLL_MS);

  const registrations: (Unregistrable | undefined)[] = [];
  try {
    registrations.push(steam.SteamClient?.Overlay?.RegisterForActivateOverlayRequests?.(() => {
      lastGameRequest = Date.now();
    }));
    registrations.push(steam.SteamClient?.Overlay?.RegisterForOverlayActivated?.((_pid, appId, active, user) => {
      if (!active || !user || !isActive() || Date.now() - lastGameRequest < GAME_REQUEST_WINDOW_MS) return;
      showBigPictureHome(appId);
    }));
  } catch {
    log("steam_button_overlay_events_unavailable");
  }

  let stopHistory: (() => void) | undefined;
  let watchedHistory: SteamHistory | undefined;
  const raiseRunningGame = (pathname: string | undefined) => {
    if (!isActive() || !pathname?.startsWith("/apprunning")) return;
    const gameId = gameIdFor(steam, main()?.MainRunningAppID ?? steam.SteamUIStore?.RunningApps?.[0]?.appid);
    if (!gameId) return;
    try {
      steam.SteamClient?.Overlay?.SetOverlayState?.(gameId, COMPOSITION_HIDDEN);
      void Promise.resolve(steam.SteamClient?.Apps?.RaiseWindowForGame?.(gameId)).catch(() => log("raise_game_failed"));
    } catch {
      log("raise_game_failed");
    }
  };
  const keepControllerOnBigPicture = () => {
    const window = main();
    if (!isActive() || !window?.BrowserWindow?.document?.hasFocus?.()) return;
    if (window.m_history?.location?.pathname?.startsWith("/apprunning")) return;
    const focused = window.m_CompositionStateStore?.GetCurrentlyFocusedAppidSubscribableValue?.()?.Value;
    if (focused === undefined || focused === STEAM_UI_APPID) return;
    const gameId = gameIdFor(steam, window.MainRunningAppID ?? steam.SteamUIStore?.RunningApps?.[0]?.appid);
    if (!gameId) return;
    try {
      steam.SteamClient?.Overlay?.SetOverlayState?.(gameId, COMPOSITION_OVERLAY);
    } catch {
      log("steam_input_overlay_failed");
    }
    for (const delay of REACTIVATE_DELAYS_MS) timers.setTimeout(activateBigPicture, delay);
  };

  // Big Picture taking focus while it shows the running game's page means the player came back to it (Game Bar,
  // Alt+Tab): that page is only Steam's logo, so it goes Home as with the Steam button. Resuming and launching keep
  // Big Picture's focus and never send this event.
  const onBigPictureFocus = () => {
    const window = main();
    if (isActive() && window?.m_history?.location?.pathname?.startsWith("/apprunning")) {
      const appId = window.MainRunningAppID ?? steam.SteamUIStore?.RunningApps?.[0]?.appid;
      if (appId) {
        showBigPictureHome(appId);
        return;
      }
    }
    keepControllerOnBigPicture();
  };

  let watchedWindow: SteamWindowInstance["BrowserWindow"];
  const watchHistory = () => {
    const window = main()?.BrowserWindow;
    if (window && window !== watchedWindow) {
      watchedWindow?.removeEventListener("focus", onBigPictureFocus);
      watchedWindow = window;
      window.addEventListener("focus", onBigPictureFocus);
    }
    keepControllerOnBigPicture();
    const history = main()?.m_history;
    if (!history || history === watchedHistory) return;
    stopHistory?.();
    watchedHistory = history;
    stopHistory = history.listen?.((location) => {
      raiseRunningGame(location.pathname);
      keepControllerOnBigPicture();
    });
  };
  watchHistory();
  const historyPoll = timers.setInterval(watchHistory, OVERLAY_POLL_MS);

  return () => {
    timers.clearInterval(overlayPoll);
    timers.clearInterval(historyPoll);
    stopHistory?.();
    watchedWindow?.removeEventListener("focus", onBigPictureFocus);
    for (const registration of registrations) {
      try {
        registration?.unregister?.();
      } catch {
        // Steam already dropped it.
      }
    }
    for (const [overlay, own] of patched) {
      if (own === undefined) delete overlay.OnHomeButtonPressed;
      else overlay.OnHomeButtonPressed = own as SteamWindowInstance["OnHomeButtonPressed"];
    }
    patched.clear();
  };
}
