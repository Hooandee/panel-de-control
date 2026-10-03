import { useCallback, useMemo, useRef } from "react";

import { kioskSteam } from "../../../src/api";
import { coloresTarget, ColoresState } from "./deckMath";
import { usePoll } from "./live";
import { createCoalescedWriter } from "./writer";

export class SteamActionError extends Error {}

export async function steamCall<T = unknown>(action: string, args: unknown[] = []): Promise<T> {
  const reply = await kioskSteam(action, args);
  if (!reply.ok) throw new SteamActionError(reply.error);
  return reply.result as T;
}

// Steam applies brightness and volume instantly, so these follow the finger closely.
const SCALAR_GAP_MS = 40;
// A poll that lands mid-drag must not yank the slider back to an older reading.
const POLL_HOLD_MS = 1500;

/** Steam's brightness or volume as 0..1, null while Steam has not answered. */
export function useSteamScalar(kind: "brightness" | "volume") {
  const lastWrite = useRef(-Infinity);
  const latest = useRef<number | null>(null);
  const read = useCallback(async () => {
    if (Date.now() - lastWrite.current < POLL_HOLD_MS) return latest.current;
    return (await steamCall<{ value: number | null }>(`${kind}.get`)).value;
  }, [kind]);
  const [value, setValue] = usePoll(read, 3000);
  latest.current = value;
  const writer = useMemo(
    () => createCoalescedWriter<number>((next) => steamCall(`${kind}.set`, [next]), SCALAR_GAP_MS),
    [kind],
  );
  const write = (next: number) => {
    lastWrite.current = Date.now();
    writer.push(next);
  };
  const commit = (next: number) => {
    write(next);
    setValue(next);
  };
  return { value, write, commit };
}

export interface RefreshRange {
  current: number | null;
  min: number | null;
  max: number | null;
  settable?: boolean;
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
  /** Mid-drag preview: throttled, no re-read; finish with `patch`. */
  preview: (changes: Record<string, unknown>) => void;
  install: () => Promise<boolean>;
}

// Every Colores write lands on the LED controller and its settings file.
const LIGHTS_GAP_MS = 150;

export function useColores(): ColoresControl {
  const read = useCallback(() => steamCall<{ installed: boolean; state?: ColoresState }>("colores.state"), []);
  const [snapshot, setSnapshot] = usePoll(read, 4000);
  const state = snapshot?.state ?? null;
  const previewer = useMemo(
    () => createCoalescedWriter<unknown[]>((args) => steamCall("colores.call", ["patch_profile", args]), LIGHTS_GAP_MS),
    [],
  );
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
      return previewer.flush().then(() => settle("patch_profile", [scope, appKey, changes], optimistic));
    },
    preview: (changes) => {
      if (!state) return;
      const [scope, appKey] = coloresTarget(state);
      previewer.push([scope, appKey, changes]);
    },
    install: async () => {
      const ok = await steamCall<boolean>("colores.install");
      setSnapshot(await read());
      return ok;
    },
  };
}
