import { Navigation } from "@decky/ui";

import { addUpscalerUserFile, getUpscalerUserFileCandidates } from "../api";
import { upscalerErrorCode } from "./errorCode";
import type { GameDetail, UserFile } from "./types";

const POLL_MS = 3000;
const LIMIT_MS = 15 * 60 * 1000;

export type UserFileWatchEvent =
  | { type: "watching"; appid: string; dependency: string }
  | { type: "stopped"; appid: string; dependency: string }
  | { type: "adopted"; appid: string; dependency: string; detail: GameDetail }
  | { type: "failed"; appid: string; dependency: string; code: string };

interface Watch {
  appid: string;
  dependency: string;
  known: Set<string>;
  until: number;
  timer: ReturnType<typeof setInterval>;
  busy: boolean;
}

let watch: Watch | null = null;
let pressed = 0;
const reinstall = new Set<string>();
const listeners = new Set<(event: UserFileWatchEvent) => void>();

function emit(event: UserFileWatchEvent): void {
  for (const listener of listeners) listener(event);
}

function stop(): Watch | null {
  const current = watch;
  if (current) clearInterval(current.timer);
  watch = null;
  return current;
}

export function onUserFileWatch(listener: (event: UserFileWatchEvent) => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function watchingFor(appid: string, dependency: string): boolean {
  return watch?.appid === appid && watch.dependency === dependency;
}

/** A changed file still has to go into the installed game: GameView reinstalls once the game and any job allow it. */
export function markPendingReinstall(appid: string): void {
  reinstall.add(appid);
}

/** Consumed once. */
export function takePendingReinstall(appid: string): boolean {
  return reinstall.delete(appid);
}

export function cancelUserFileWatch(): void {
  const current = stop();
  if (current) emit({ type: "stopped", appid: current.appid, dependency: current.dependency });
}

async function tick(): Promise<void> {
  const current = watch;
  if (!current || current.busy) return;
  if (Date.now() > current.until) {
    cancelUserFileWatch();
    return;
  }
  current.busy = true;
  try {
    const { candidates } = await getUpscalerUserFileCandidates(current.dependency);
    if (watch !== current) return;
    // A half-written download doesn't open as an archive yet, so it never shows up here.
    const fresh = candidates.find((candidate) => !current.known.has(candidate.path));
    if (!fresh) return;
    let detail: GameDetail;
    try {
      detail = await addUpscalerUserFile(current.appid, current.dependency, fresh.path);
    } catch (error) {
      const code = upscalerErrorCode(error);
      // An install is running: the next tick tries again.
      if (code === "busy") return;
      if (watch === current) stop();
      emit({ type: "failed", appid: current.appid, dependency: current.dependency, code });
      return;
    }
    if (watch === current) stop();
    if (detail.install) reinstall.add(current.appid);
    emit({ type: "adopted", appid: current.appid, dependency: current.dependency, detail });
  } catch {
    /* the next tick tries again */
  } finally {
    current.busy = false;
  }
}

/** Opens the file's download page in Steam's browser and picks the archive up as soon as it lands in Downloads. */
export async function downloadUserFile(appid: string, file: Pick<UserFile, "id" | "page_url" | "download_url">): Promise<void> {
  cancelUserFileWatch();
  const press = ++pressed;
  let known = new Set<string>();
  try {
    known = new Set((await getUpscalerUserFileCandidates(file.id)).candidates.map((candidate) => candidate.path));
  } catch {
    /* every download then counts as new */
  }
  // A later press owns the watch.
  if (press !== pressed) return;
  watch = { appid, dependency: file.id, known, until: Date.now() + LIMIT_MS, timer: setInterval(() => void tick(), POLL_MS), busy: false };
  emit({ type: "watching", appid, dependency: file.id });
  Navigation.NavigateToExternalWeb(file.download_url ?? file.page_url);
}
