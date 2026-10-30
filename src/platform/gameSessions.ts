import { readRunningGame, type RunningGame } from "../tdp/runningGame";

export interface GameSessionPort {
  current(): RunningGame | null;
  subscribe(listener: (game: RunningGame | null) => void): () => void;
}

interface LifetimeRegistration {
  unregister?: () => void;
}

interface SteamGameSessions {
  RegisterForAppLifetimeNotifications?: (cb: (update: unknown) => void) => LifetimeRegistration | undefined;
}

const SETTLE_MS = 400;

function gameSessions(): SteamGameSessions | undefined {
  try {
    return (globalThis as unknown as { SteamClient?: { GameSessions?: SteamGameSessions } }).SteamClient?.GameSessions;
  } catch {
    return undefined;
  }
}

/** Running-game signal shared by every domain: Steam lifetime events, re-read from the router. */
export function createGameSessionPort(read: () => RunningGame | null = readRunningGame): GameSessionPort {
  return {
    current: read,
    subscribe(listener) {
      let last = read();
      let timer: ReturnType<typeof setTimeout> | null = null;
      const check = () => {
        const now = read();
        if ((now?.appid ?? null) === (last?.appid ?? null)) return;
        last = now;
        listener(now);
      };
      let registration: LifetimeRegistration | undefined;
      try {
        registration = gameSessions()?.RegisterForAppLifetimeNotifications?.(() => {
          if (timer !== null) clearTimeout(timer);
          timer = setTimeout(check, SETTLE_MS);
        });
      } catch {
        registration = undefined;
      }
      const poll = setInterval(check, 5000);
      return () => {
        clearInterval(poll);
        if (timer !== null) clearTimeout(timer);
        try {
          registration?.unregister?.();
        } catch {
          /* Steam already tore it down */
        }
      };
    },
  };
}
