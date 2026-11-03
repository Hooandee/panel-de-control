import { getUpscalersJob, recordUpscalerArgs } from "../api";
import { readAppDetails, writeLaunchOptions } from "../launch/steamApi";
import { launchAfterJob } from "./model";
import type { UpscalerJob } from "./types";

const POLL_MS = 250;

export interface JobGame { appid: string; liveAppid: number; isNonSteam: boolean }
export type JobNotice = { key: string; params?: Record<string, string | number> } | null;
export interface JobUpdate { job: UpscalerJob; finished: boolean; notice: JobNotice }

const listeners = new Set<(update: JobUpdate) => void>();
const tracked = new Set<string>();

/** Follows a job to the end even when the Quick Access Menu closes, then writes the game's launch options. */
export function trackJob(job: UpscalerJob, game: JobGame): void {
  if (tracked.has(job.id)) return;
  tracked.add(job.id);
  let finishing = false;
  const timer = globalThis.setInterval(async () => {
    const next = await getUpscalersJob().catch(() => null);
    if (finishing || !next || next.id !== job.id) return;
    if (next.state === "running") {
      emit({ job: next, finished: false, notice: null });
      return;
    }
    finishing = true;
    globalThis.clearInterval(timer);
    const notice = await applyLaunch(next, game).catch(() => ({ key: "up.error.generic" }));
    tracked.delete(job.id);
    emit({ job: next, finished: true, notice });
  }, POLL_MS);
}

export function onJobUpdate(listener: (update: JobUpdate) => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function emit(update: JobUpdate) {
  for (const listener of listeners) listener(update);
}

async function applyLaunch(job: UpscalerJob, game: JobGame): Promise<JobNotice> {
  const result = job.state === "done" ? job.result : job.leftover ? { overrides: [], args: [], ...job.leftover } : undefined;
  if (!result || result.launcher) return result?.kept?.length ? { key: "up.kept", params: { count: result.kept.length } } : null;
  if (!result.overrides && !job.leftover) return null;
  const details = await readAppDetails(game.liveAppid);
  const kind = job.state === "done" ? job.kind : "install";
  const next = details ? launchAfterJob(details.launch, result, kind) : null;
  if (next === null || !writeLaunchOptions(game.liveAppid, next.value, game.isNonSteam)) {
    if (kind === "install" && job.state === "done") {
      const overrides = result.overrides ?? [];
      const value = `WINEDLLOVERRIDES="${overrides.map((o) => o.split("=")[0]).join(",")}=n,b" %command% ${(result.args ?? []).join(" ")}`;
      return { key: "up.launch.failed", params: { value: value.trim() } };
    }
    return { key: "up.error.generic" };
  }
  if (kind === "install" && job.state === "done") {
    await recordUpscalerArgs(game.appid, next.added, next.addedOverrides, next.addedEnv).catch(() => undefined);
  }
  return result.kept?.length ? { key: "up.kept", params: { count: result.kept.length } } : null;
}
