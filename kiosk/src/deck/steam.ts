import { useCallback, useEffect, useRef } from "react";

import { kioskSteam } from "../../../src/api";
import { coloresTarget, ColoresState } from "./deckMath";
import { usePoll } from "./live";

export class SteamActionError extends Error {}

export async function steamCall<T = unknown>(action: string, args: unknown[] = []): Promise<T> {
  const reply = await kioskSteam(action, args);
  if (!reply.ok) throw new SteamActionError(reply.error);
  return reply.result as T;
}

const WRITE_DEBOUNCE_MS = 90;

/** Steam's brightness or volume as 0..1, null while Steam has not answered. */
export function useSteamScalar(kind: "brightness" | "volume") {
  const read = useCallback(async () => (await steamCall<{ value: number | null }>(`${kind}.get`)).value, [kind]);
  const [value, setValue] = usePoll(read, 3000);
  const timer = useRef<number | null>(null);
  useEffect(() => () => {
    if (timer.current != null) window.clearTimeout(timer.current);
  }, []);
  const set = (next: number) => {
    setValue(next);
    if (timer.current != null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void steamCall(`${kind}.set`, [next]).catch(() => {}), WRITE_DEBOUNCE_MS);
  };
  return { value, set };
}

export interface RefreshRange {
  current: number | null;
  min: number | null;
  max: number | null;
}

export function useRefreshRate() {
  const read = useCallback(() => steamCall<RefreshRange | null>("refresh.get"), []);
  const [range, setRange] = usePoll(read, 5000);
  const set = async (hz: number) => {
    await steamCall("refresh.set", [hz]);
    setRange(await read());
  };
  return { range, set };
}

export interface ColoresControl {
  installed: boolean | null;
  state: ColoresState | null;
  setPower: (on: boolean) => Promise<void>;
  patch: (changes: Record<string, unknown>, optimistic: Partial<ColoresState>) => Promise<void>;
  install: () => Promise<boolean>;
}

export function useColores(): ColoresControl {
  const read = useCallback(() => steamCall<{ installed: boolean; state?: ColoresState }>("colores.state"), []);
  const [snapshot, setSnapshot] = usePoll(read, 4000);
  const state = snapshot?.state ?? null;
  const settle = async (method: string, args: unknown[], optimistic: Partial<ColoresState>) => {
    if (snapshot?.state) setSnapshot({ ...snapshot, state: { ...snapshot.state, ...optimistic } });
    try {
      await steamCall("colores.call", [method, args]);
    } finally {
      setSnapshot(await read().catch(() => snapshot));
    }
  };
  return {
    installed: snapshot?.installed ?? null,
    state,
    setPower: (on) => settle("set_power", [on], { power: on }),
    patch: (changes, optimistic) => {
      if (!state) return Promise.resolve();
      const [scope, appKey] = coloresTarget(state);
      return settle("patch_profile", [scope, appKey, changes], optimistic);
    },
    install: async () => {
      const ok = await steamCall<boolean>("colores.install");
      setSnapshot(await read());
      return ok;
    },
  };
}
