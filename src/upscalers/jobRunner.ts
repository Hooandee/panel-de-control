import { getUpscalersGame, getUpscalersJob, installUpscaler, uninstallUpscaler, recordUpscalerArgs, type MakoProfile } from "../api";
import { prepareScalerTransition, type ScalerTransition } from "./scalerTransition";
import { saveMakoProfile } from "./makoProfile";
import { launchAfterJob } from "./model";
import { applyManagedLaunch } from "./managedLaunch";
import type { UpscalerChoice, UpscalerJob } from "./types";

const POLL_MS = 250;

export interface JobGame { appid: string; liveAppid: number; isNonSteam: boolean }
export type JobNotice = { key: string; params?: Record<string, string | number> } | null;
export interface JobUpdate { job: UpscalerJob; finished: boolean; notice: JobNotice }

const listeners = new Set<(update: JobUpdate) => void>();
const tracked = new Set<string>();
const transitions = new Map<string, ScalerTransition>();
const installRequests = new Map<string, { jobId: string; choice: UpscalerChoice }>();
const unseenNotices = new Map<string, { jobId: string; notice: NonNullable<JobNotice> }>();

/** The last job's closing notice for this game, handed out once, so a page opened later still shows it. */
export function takeJobNotice(appid: string): JobNotice {
  const entry = unseenNotices.get(appid);
  unseenNotices.delete(appid);
  return entry?.notice ?? null;
}

export function readInstallRequest(appid: string, jobId?: string): UpscalerChoice | null {
  const request = installRequests.get(appid);
  return request && (jobId === undefined || request.jobId === jobId) ? { ...request.choice } : null;
}

export function readInstallJobId(appid: string): string | undefined {
  return installRequests.get(appid)?.jobId;
}

export function clearInstallRequest(appid: string, jobId: string): void {
  if (installRequests.get(appid)?.jobId === jobId) installRequests.delete(appid);
}

export async function startInstallJob(game: JobGame, choice: UpscalerChoice): Promise<UpscalerJob> {
  const request = { ...choice };
  const detail = await getUpscalersGame(game.appid);
  const transition = await prepareScalerTransition(game, "installed", !!detail?.recipe_info?.automatic_builds?.includes(request.build));
  try {
    const job = await installUpscaler(game.appid, { ...request });
    if (transition) transitions.set(job.id, transition);
    trackJob(job, game, request);
    return job;
  } catch (error) {
    await transition?.finish(false);
    throw error;
  }
}

/** Follows a job to the end even when the Quick Access Menu closes, then writes the game's launch options. */
export function trackJob(job: UpscalerJob, game: JobGame, request?: UpscalerChoice): void {
  if (request && job.kind === "install") installRequests.set(job.appid, { jobId: job.id, choice: { ...request } });
  else if (installRequests.get(job.appid)?.jobId !== job.id) installRequests.delete(job.appid);
  if (tracked.has(job.id)) return;
  tracked.add(job.id);
  if (unseenNotices.get(job.appid)?.jobId !== job.id) unseenNotices.delete(job.appid);
  let finishing = false;
  const timer = globalThis.setInterval(async () => {
    let next = await getUpscalersJob().catch(() => null);
    if (finishing || !next || next.id !== job.id) return;
    if (next.state === "running") {
      emit({ job: next, finished: false, notice: null });
      return;
    }
    finishing = true;
    globalThis.clearInterval(timer);
    let notice = await applyLaunch(next, game).catch(() => ({ key: "up.error.generic" }));
    const transition = transitions.get(job.id);
    if (transition) {
      transitions.delete(job.id);
      const success = next.state === "done" && !!next.result && !notice;
      try {
        await transition.finish(success);
        if (!success && next.state === "done") next = { ...next, state: "error", error: "transition_failed" };
      } catch (error) {
        next = { ...next, state: "error", error: error instanceof Error ? error.message : "transition_restore_failed" };
        notice = { key: `up.error.${next.error}` };
      }
    }
    tracked.delete(job.id);
    if (next.state === "done") clearInstallRequest(job.appid, job.id);
    if (notice) unseenNotices.set(job.appid, { jobId: job.id, notice });
    emit({ job: next, finished: true, notice });
  }, POLL_MS);
}

export function onJobUpdate(listener: (update: JobUpdate) => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Wait for the tracked installer and its launch write; a timeout must not race a live installer. */
export function waitForJobCompletion(jobId: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const stop = onJobUpdate((update) => {
      if (update.job.id !== jobId || !update.finished) return;
      stop();
      if (update.job.state !== "done") reject(new Error(update.job.error || "install_failed"));
      else if (!update.job.result || (update.notice && update.notice.key !== "up.kept")) reject(new Error("launch_failed"));
      else resolve();
    });
  });
}

function emit(update: JobUpdate) {
  for (const listener of listeners) listener(update);
}

async function applyLaunch(job: UpscalerJob, game: JobGame): Promise<JobNotice> {
  const result = job.state === "done" ? job.result : job.leftover ? { overrides: [], args: [], ...job.leftover } : undefined;
  if (!result || result.launcher) return result?.kept?.length ? { key: "up.kept", params: { count: result.kept.length } } : null;
  if (!result.overrides && !result.env && !job.leftover) return null;
  const kind = job.state === "done" ? job.kind : "install";
  const env = kind === "install" ? Object.fromEntries(Object.entries(result.env ?? {}).filter((pair): pair is [string, string] => pair[1] !== null)) : {};
  let added: string[] = [];
  let addedOverrides: string[] = [];
  const managed = await applyManagedLaunch(game.appid, game.liveAppid, "upscaler", { env }, {
    isNonSteam: game.isNonSteam,
    ...(kind === "install" && job.state === "done" && transitions.has(job.id)
      ? { beforeApply: () => recordUpscalerArgs(game.appid, added, addedOverrides, []).then(() => undefined) } : {}),
    transform: (launch) => {
      const next = launchAfterJob(launch, { ...result, env: undefined }, kind);
      if (!next) return null;
      added = next.added;
      addedOverrides = next.addedOverrides;
      return next.value;
    },
  });
  if (!managed.ok) {
    if (kind === "install" && job.state === "done") {
      const overrides = result.overrides ?? [];
      const value = `WINEDLLOVERRIDES="${overrides.map((o) => o.split("=")[0]).join(",")}=n,b" %command% ${(result.args ?? []).join(" ")}`;
      return { key: "up.launch.failed", params: { value: value.trim() } };
    }
    return { key: "up.error.generic" };
  }
  if (kind === "install" && job.state === "done" && !transitions.has(job.id)) {
    await recordUpscalerArgs(game.appid, added, addedOverrides, []).catch(() => undefined);
  }
  return result.kept?.length ? { key: "up.kept", params: { count: result.kept.length } } : null;
}

export async function saveExclusiveMakoProfile(game: JobGame, config: Partial<MakoProfile>): Promise<void> {
  if (!config.scaling_enabled) {
    await saveMakoProfile(game.appid, game.liveAppid, config, game.isNonSteam);
    return;
  }
  const detail = await getUpscalersGame(game.appid);
  if (!detail.install && detail.analysis.foreign) throw new Error("foreign");
  const transition = await prepareScalerTransition(game, "mako");
  try {
    // Opening the transition takes HelixSR out by itself; only what is still installed needs an uninstall.
    if (detail.install && (await getUpscalersGame(game.appid)).install) {
      const job = await uninstallUpscaler(game.appid);
      const completed = waitForJobCompletion(job.id);
      trackJob(job, game);
      await completed;
      const result = await getUpscalersJob();
      if (result?.id !== job.id || result.result?.kept?.length) throw new Error("foreign");
    }
    await saveMakoProfile(game.appid, game.liveAppid, config, game.isNonSteam);
  } catch (error) {
    await transition?.finish(false);
    throw error;
  }
  await transition?.finish(true);
}
