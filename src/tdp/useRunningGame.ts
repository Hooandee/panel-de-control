import { useEffect, useState } from "react";
import { Router } from "@decky/ui";
import { setCurrentGame } from "../api";

export interface RunningGame {
  appid: string;
  name: string;
}

/**
 * Reads the foreground running game from Router.MainRunningApp.
 * Returns null when no game is running (Steam UI / desktop).
 * Never throws — wraps in try/catch for API unavailability.
 */
function readRunningGame(): RunningGame | null {
  try {
    const app = Router?.MainRunningApp;
    if (app && app.appid) {
      return {
        appid: String(app.appid),
        name: app.display_name ?? String(app.appid),
      };
    }
  } catch {
    /* API unavailable */
  }
  return null;
}

/**
 * Reports the currently-running game (appid + display name), or null when
 * Steam UI / desktop is in the foreground.
 *
 * Subscribes to SteamClient.GameSessions.RegisterForAppLifetimeNotifications
 * for live updates; falls back to a 2 s polling interval if that API is absent.
 * Unsubscribes / clears the interval on unmount.
 *
 * On every game change, calls setCurrentGame(appid | null) from api.ts so the
 * backend can activate the appropriate per-game TDP profile.
 *
 * Degrades gracefully: if the Steam/Decky API is unavailable or throws, the
 * hook returns null and never throws itself.
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
      setGame((prev) => {
        const changed = (prev?.appid ?? null) !== (next?.appid ?? null);
        if (changed) {
          try {
            void setCurrentGame(next ? next.appid : null);
          } catch {
            /* backend not ready yet */
          }
        }
        return next;
      });
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
