import { readRunningGame } from "../tdp/runningGame";

const EMPTY = { on: false, busy: false, failed: false };
let game: string | null = null;
let generation = 0;
let state = EMPTY;
const listeners = new Set<() => void>();

function publish(next: typeof EMPTY): void {
  state = next;
  for (const listener of listeners) listener();
}

export function syncFpsCounterSession(appid: string | null): void {
  if (game === appid) return;
  game = appid;
  generation++;
  publish(EMPTY);
}

export function fpsCounterSnapshot(appid: string): typeof EMPTY {
  return game === appid ? state : EMPTY;
}

export function subscribeFpsCounter(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export async function toggleFpsCounter(appid: string, press: () => Promise<unknown>): Promise<void> {
  if (game !== appid) syncFpsCounterSession(appid);
  if (state.busy) return;
  const session = generation;
  const on = state.on;
  publish({ on, busy: true, failed: false });
  try {
    await press();
    if (session === generation) publish({ on: !on, busy: false, failed: false });
  } catch {
    if (session === generation) publish({ on, busy: false, failed: true });
  }
}

export function startFpsCounterSession(): () => void {
  const sync = () => {
    const current = readRunningGame();
    syncFpsCounterSession(current ? String(current.liveAppid) : null);
  };
  sync();
  const timer = window.setInterval(sync, 2000);
  return () => {
    window.clearInterval(timer);
    syncFpsCounterSession(null);
  };
}
