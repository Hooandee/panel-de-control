import { setCurrentGame } from "../api";
import { GameReport, isSameGameReport } from "./gameReport";
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
 * Reports on game identity changes and when Steam hydrates a better display name.
 * Degrades: if the Steam/Decky API is unavailable or throws, it never throws.
 */
const GAME_POLL_MS = 2000;
const GAME_REPORT_TIMEOUT_MS = 30000;
const MAX_PENDING_GAME_REPORTS = 2;

interface PendingGameReport {
  id: number;
  target: GameReport;
  timeout: ReturnType<typeof setTimeout> | null;
}

export function startGameWatcher(): () => void {
  let alive = true;
  let unregister: (() => void) | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let committed: GameReport | undefined;
  let desired: GameReport = { appid: null, name: null };
  let inFlight: PendingGameReport | undefined;
  let nextRequestId = 0;
  const pendingRequestIds = new Set<number>();

  const clearActiveRequest = (request: PendingGameReport): boolean => {
    if (inFlight?.id !== request.id) return false;
    if (request.timeout !== null) clearTimeout(request.timeout);
    inFlight = undefined;
    return true;
  };

  const sendDesired = (): void => {
    if (
      !alive
      || inFlight
      || pendingRequestIds.size >= MAX_PENDING_GAME_REPORTS
      || (committed && isSameGameReport(desired, committed))
    ) return;
    const request: PendingGameReport = {
      id: ++nextRequestId,
      target: desired,
      timeout: null,
    };
    inFlight = request;
    pendingRequestIds.add(request.id);
    request.timeout = setTimeout(() => {
      if (!alive || !clearActiveRequest(request)) return;
      sendDesired();
    }, GAME_REPORT_TIMEOUT_MS);
    try {
      Promise.resolve(setCurrentGame(request.target.appid, request.target.name))
        .then(() => {
          pendingRequestIds.delete(request.id);
          if (!alive) return;
          clearActiveRequest(request);
          committed = request.target;
          sendDesired();
        })
        .catch(() => {
          pendingRequestIds.delete(request.id);
          if (!alive) return;
          clearActiveRequest(request);
        });
    } catch {
      pendingRequestIds.delete(request.id);
      clearActiveRequest(request);
    }
  };

  const report = (confirmIdle = false): void => {
    if (!alive) return;
    const next = readRunningGame();
    desired = {
      appid: next ? next.appid : null,
      name: next ? next.name : null,
    };
    if (desired.appid === null && committed === undefined && !inFlight && !confirmIdle) return;
    sendDesired();
  };

  report();
  pollTimer = setInterval(() => report(true), GAME_POLL_MS);

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
    }
  } catch { /* polling remains active */ }

  return () => {
    alive = false;
    if (unregister) unregister();
    if (pollTimer !== null) clearInterval(pollTimer);
    if (inFlight?.timeout != null) clearTimeout(inFlight.timeout);
    pendingRequestIds.clear();
  };
}
