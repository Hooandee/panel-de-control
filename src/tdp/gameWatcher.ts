import { setCurrentGame } from "../api";
import { GameReport, isSameGameReport, shouldReportGame } from "./gameReport";
import { readRunningGame } from "./runningGame";

/**
 * Persistent "current game" watcher, started once at plugin load (definePlugin)
 * and torn down on unload. It lives OUTSIDE the QAM content tree, so it runs
 * while Steam is running regardless of whether the user has opened the panel.
 *
 * This is the SINGLE source that reports the running game to the backend via
 * setCurrentGame(appid | null). The backend needs this so the auto-TDP loop,
 * the telemetry sampler and the fan auto-apply activate the right per-game
 * profile — otherwise, after a plugin_loader restart, the backend thinks no
 * game is running until the user opens the QAM (which is what mounts the UI
 * hooks), leaving auto-TDP inert on a game that is already running.
 *
 * useRunningGame is now a LOCAL UI read only — it does NOT report to the
 * backend, so there is no double-report / race with this watcher.
 *
 * Robustness (the crux of the restart bug — two failure modes):
 *  1. Router.MainRunningApp hydrates ASYNC. At plugin load the initial read can
 *     still be null even though a game is already running, and
 *     RegisterForAppLifetimeNotifications does NOT re-emit for an already-running
 *     game → the backend would stay at appid=None forever. So we run a bounded
 *     startup poll (every ~2 s) until we have SUCCESSFULLY reported a real appid,
 *     independent of whether the event API exists.
 *  2. The backend RPC may not be ready at load. We commit the report ONLY after
 *     setCurrentGame RESOLVES OK; on rejection we leave it so the next tick retries.
 *
 * Reports on game identity changes and when Steam hydrates a better display name.
 * Degrades: if the Steam/Decky API is unavailable or throws, it never throws.
 */
// Startup poll cadence and how long to keep polling for the first successful
// real-appid report before falling back to event-only steady state.
const STARTUP_POLL_MS = 2000;
const STARTUP_POLL_MAX = 30; // ~60 s of bounded startup retries

export function startGameWatcher(): () => void {
  let alive = true;
  let unregister: (() => void) | null = null;
  let startupTimer: ReturnType<typeof setInterval> | null = null;
  let eventFallbackTimer: ReturnType<typeof setInterval> | null = null;
  let committed: GameReport = { appid: null, name: null };
  let inFlight: GameReport | undefined;
  let sawRealAppid = false; // have we ever SUCCESSFULLY reported a non-null appid?
  let startupTicks = 0;

  const stopStartupPoll = (): void => {
    if (startupTimer !== null) {
      clearInterval(startupTimer);
      startupTimer = null;
    }
  };

  const report = (): void => {
    if (!alive) return;
    const next = readRunningGame();
    const target: GameReport = {
      appid: next ? next.appid : null,
      name: next ? next.name : null,
    };
    if (!shouldReportGame(target, committed, inFlight)) return;
    inFlight = target;
    try {
      // Pass the display name too so the HUD's Perfil metric can show it; the backend
      // ignores it beyond that (the appid stays the profile key).
      Promise.resolve(setCurrentGame(target.appid, target.name))
        .then(() => {
          if (!alive || !inFlight || !isSameGameReport(inFlight, target)) return;
          committed = target;
          inFlight = undefined;
          if (target.appid !== null) {
            sawRealAppid = true;
            stopStartupPoll(); // got a real game → startup retries no longer needed
          }
        })
        .catch(() => {
          if (inFlight && isSameGameReport(inFlight, target)) inFlight = undefined;
        });
    } catch {
      if (inFlight && isSameGameReport(inFlight, target)) inFlight = undefined;
    }
  };

  // Startup poll: keep trying the initial read+report until we SUCCESSFULLY report
  // a real appid (Router hydration + backend readiness), then stop. Bounded so a
  // genuine "no game running" boot doesn't poll forever.
  report(); // fire once immediately
  startupTimer = setInterval(() => {
    startupTicks += 1;
    if (!alive || sawRealAppid || startupTicks >= STARTUP_POLL_MAX) {
      stopStartupPoll();
      return;
    }
    report();
  }, STARTUP_POLL_MS);

  // Subscribe to app lifetime notifications for immediate steady-state updates.
  try {
    const reg =
      SteamClient?.GameSessions?.RegisterForAppLifetimeNotifications?.(
        () => report(),
      );
    if (reg && typeof reg.unregister === "function") {
      unregister = () => {
        try {
          reg.unregister();
        } catch {
          /* ignore */
        }
      };
    } else {
      // Notification API absent — poll steady-state too (in addition to startup).
      eventFallbackTimer = setInterval(report, STARTUP_POLL_MS);
    }
  } catch {
    // Notification API threw — fall back to steady-state polling.
    eventFallbackTimer = setInterval(report, STARTUP_POLL_MS);
  }

  return () => {
    alive = false;
    if (unregister) unregister();
    stopStartupPoll();
    if (eventFallbackTimer !== null) clearInterval(eventFallbackTimer);
  };
}
