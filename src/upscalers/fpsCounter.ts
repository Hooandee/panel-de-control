import { readRunningGame } from "../tdp/runningGame";

const EMPTY = { on: false, busy: false, failed: false };
// OptiScaler's counter is a blind toggle that never reports back, so Panel keeps the switch position itself:
// stored so a Panel or Steam UI reload mid-game keeps it, and kept through brief moments without a running game
// (resume from sleep, focus changes) instead of falling back to "off" while the counter stays on screen.
const STORE_KEY = "pdc:upscalers:fpsCounter";
const GONE_AFTER_MS = 10000;
let game: string | null = null;
let generation = 0;
let state = EMPTY;
const listeners = new Set<() => void>();

// sessionStorage: survives a reload of Steam's UI, gone once Steam restarts (and the game with it).
function readStore(): string | null {
  try { return window.sessionStorage.getItem(STORE_KEY); } catch { return null; }
}

function writeStore(value: string): void {
  try {
    if (value) window.sessionStorage.setItem(STORE_KEY, value);
    else window.sessionStorage.removeItem(STORE_KEY);
  } catch { /* storage unavailable: the switch simply starts off */ }
}

function remembered(appid: string): boolean {
  try {
    const saved = JSON.parse(readStore() ?? "null") as { appid?: unknown; on?: unknown } | null;
    return saved?.appid === appid && saved.on === true;
  } catch {
    return false;
  }
}

function remember(): void {
  writeStore(game && state.on ? JSON.stringify({ appid: game, on: true }) : "");
}

function publish(next: typeof EMPTY): void {
  state = next;
  if (!next.busy) remember();
  for (const listener of listeners) listener();
}

export function syncFpsCounterSession(appid: string | null): void {
  if (game === appid) return;
  game = appid;
  generation++;
  publish(appid && remembered(appid) ? { on: true, busy: false, failed: false } : EMPTY);
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
  let missingSince: number | null = null;
  const sync = () => {
    const current = readRunningGame();
    if (current) {
      missingSince = null;
      syncFpsCounterSession(String(current.liveAppid));
      return;
    }
    missingSince ??= Date.now();
    if (Date.now() - missingSince >= GONE_AFTER_MS) syncFpsCounterSession(null);
  };
  sync();
  const timer = window.setInterval(sync, 2000);
  return () => {
    window.clearInterval(timer);
    // Panel unloading is not the game ending: forget the session here but keep what was stored.
    game = null;
    generation++;
    state = EMPTY;
    for (const listener of listeners) listener();
  };
}
