import { readRunningGame } from "../tdp/runningGame";
import { upscalerErrorCode } from "./errorCode";
import { startInstallJob, trackJob, waitForJobCompletion, type JobGame } from "./jobRunner";
import type { UpscalerChoice } from "./types";

/**
 * A new version or model chosen while its game runs. The game holds OptiScaler's files open, so the install waits for
 * the game to close; it then runs on its own, page open or not, one game at a time.
 */
interface Pending { game: JobGame; choice: UpscalerChoice }

const STORAGE_KEY = "pdc-upscalers-pending-installs";
const POLL_MS = 2000;
// The game is still closing, another job holds the service, or a checkpoint is being recovered: try again shortly.
const TRANSIENT = new Set(["running", "busy", "transition_recovered", "transition_pending", "download_failed", "updating"]);
const pending = new Map<string, Pending>();
const failures = new Map<string, string>();
const restarting = new Set<string>();
const listeners = new Set<() => void>();
let watcher: ReturnType<typeof setInterval> | null = null;
let working = false;
let restored = false;

function persist(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...pending.values()]));
  } catch { /* storage is a convenience: the in-memory queue still applies */ }
}

function restore(): void {
  if (restored) return;
  restored = true;
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as Pending[];
    for (const item of Array.isArray(saved) ? saved : []) {
      if (item?.game?.appid && item.choice?.build && !pending.has(item.game.appid)) pending.set(item.game.appid, item);
    }
  } catch { /* unreadable storage: nothing queued */ }
  if (pending.size) watch();
}

function notify(): void {
  for (const listener of listeners) listener();
}

async function run(item: Pending): Promise<void> {
  const job = await startInstallJob(item.game, item.choice);
  trackJob(job, item.game, item.choice);
  await waitForJobCompletion(job.id);
}

async function attempt(item: Pending): Promise<void> {
  try {
    await run(item);
    failures.delete(item.game.appid);
  } catch (error) {
    const code = upscalerErrorCode(error);
    if (TRANSIENT.has(code)) {
      if (!pending.has(item.game.appid)) put(item);
    } else {
      failures.set(item.game.appid, code);
      notify();
    }
    throw error;
  }
}

function watch(): void {
  if (watcher) return;
  watcher = setInterval(() => {
    if (working) return;
    const running = readRunningGame()?.liveAppid;
    const next = [...pending.values()].find((item) => item.game.liveAppid !== running && !restarting.has(item.game.appid));
    if (next) {
      working = true;
      take(next.game.appid);
      void attempt(next).catch(() => undefined).finally(() => {
        working = false;
        if (!pending.size) stop();
      });
    }
    if (!pending.size && !working) stop();
  }, POLL_MS);
}

function stop(): void {
  if (watcher) clearInterval(watcher);
  watcher = null;
}

function put(item: Pending): void {
  pending.set(item.game.appid, item);
  persist();
  notify();
  watch();
}

function take(appid: string): Pending | undefined {
  const item = pending.get(appid);
  pending.delete(appid);
  persist();
  notify();
  return item;
}

/** Called when the plugin loads: a queue left by a reload or a Steam restart still installs. */
export function resumePendingInstalls(): void {
  restore();
}

export function queueForGameExit(game: JobGame, choice: UpscalerChoice): void {
  restore();
  failures.delete(game.appid);
  put({ game, choice });
}

export function pendingInstall(appid: string): UpscalerChoice | null {
  restore();
  return pending.get(appid)?.choice ?? null;
}

/** The last queued install that failed for good, once. */
export function takePendingFailure(appid: string): string | null {
  const code = failures.get(appid) ?? null;
  failures.delete(appid);
  return code;
}

export function cancelPendingInstall(appid: string): void {
  if (pending.has(appid)) take(appid);
}

/** Reserves the game's queued install for a restart, so the background watcher leaves it alone. */
export function holdForRestart(appid: string): () => void {
  restarting.add(appid);
  return () => { restarting.delete(appid); };
}

/** For a restart: the game is already closed, so the queued install runs now and the game opens afterwards. */
export async function runPendingInstall(appid: string): Promise<void> {
  while (working && !pending.has(appid)) await new Promise((resolve) => setTimeout(resolve, 250));
  const item = take(appid);
  if (item) await attempt(item);
}

export function onPendingInstalls(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
