import { useEffect, useState } from "react";
import { readRunningGame, RunningGame } from "./runningGame";

export type { RunningGame };

/**
 * Reads the foreground running game (appid + display name) for the UI, or null
 * when Steam UI / desktop is in the foreground.
 *
 * LOCAL UI READ ONLY — it does NOT report to the backend. The backend's notion
 * of the current game is owned by the persistent watcher (startGameWatcher,
 * wired in definePlugin), which runs regardless of whether the QAM is open.
 * This hook only exists so components can display the running game; keeping the
 * backend report out of it means there is a single reporter and no race.
 *
 * Subscribes to SteamClient.GameSessions.RegisterForAppLifetimeNotifications
 * for live updates; falls back to a 2 s polling interval if that API is absent.
 * Unsubscribes / clears the interval on unmount. Never throws.
 */
export function useRunningGame(): RunningGame | null {
  const [game, setGame] = useState<RunningGame | null>(null);

  useEffect(() => {
    let alive = true;
    let unregister: (() => void) | null = null;
    let timer: ReturnType<typeof setInterval> | null = null;

    const sync = (): void => {
      if (!alive) return;
      const next = readRunningGame();
      // Dedupe by VALUE: RegisterForAppLifetimeNotifications can fire in bursts
      // (many callbacks/sec during certain game states). Returning a NEW object
      // each time would re-render every consumer on every callback — and since the
      // shell (ControlCenter) now consumes this, that re-renders the WHOLE panel in
      // a tight loop → CEF pegs at ~100%+ and the QAM freezes (silent, no error,
      // intermittent with the burst). Keep the SAME reference when unchanged so
      // React bails out and no storm can form.
      setGame((prev) =>
        prev?.appid === next?.appid &&
        prev?.liveAppid === next?.liveAppid &&
        prev?.name === next?.name
          ? prev
          : next,
      );
    };

    // Initial read.
    sync();

    // Subscribe to lifetime notifications for immediate updates.
    try {
      const reg =
        SteamClient?.GameSessions?.RegisterForAppLifetimeNotifications?.(
          () => sync(),
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
        // Notification API absent — fall back to polling.
        timer = setInterval(sync, 2000);
      }
    } catch {
      // Notification API threw — fall back to polling.
      timer = setInterval(sync, 2000);
    }

    return () => {
      alive = false;
      if (unregister) unregister();
      if (timer !== null) clearInterval(timer);
    };
  }, []);

  return game;
}
