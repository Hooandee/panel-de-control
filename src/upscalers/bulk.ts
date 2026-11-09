import { uninstallUpscaler, type GameCompat } from "../api";
import type { GameEntry } from "../launch/steamApi";
import { defaultChoice } from "./model";
import { onJobUpdate, startInstallJob, trackJob, type JobUpdate } from "./jobRunner";
import type { UpscalerChoice, UpscalerJob, UpscalersOverview } from "./types";
import { upscalerErrorCode } from "./errorCode";

export type BulkAction = "install" | "repair" | "update" | "remove";
export const BULK_ACTIONS: BulkAction[] = ["install", "update", "repair", "remove"];

export interface BulkStep { game: GameEntry; choice: UpscalerChoice | null }
export interface BulkProgress { action: BulkAction; index: number; total: number; current: string | null; done: number; skipped: { name: string; reason: string }[] }

function optiscaler(overview: UpscalersOverview, build: string): boolean {
  return (overview.builds.find((b) => b.id === build)?.engine ?? "optiscaler") === "optiscaler";
}

function keep(options: Partial<UpscalerChoice> | undefined, build: string): UpscalerChoice {
  return {
    build, quality: options?.quality ?? null, sharpness: options?.sharpness ?? "soft",
    fg: options?.fg ?? "off", fg_route: options?.fg_route ?? null, model: options?.model ?? null,
  };
}

/** The games each action would touch: installs only through OptiScaler builds, the rest stays per game. */
export function bulkSteps(action: BulkAction, games: GameEntry[], overview: UpscalersOverview, compat: Record<string, GameCompat>): BulkStep[] {
  return games.flatMap((game): BulkStep[] => {
    const appid = String(game.liveAppid);
    const preferred = overview.builds.find((b) => b.id === (compat[appid]?.preferred ?? overview.preferred) && b.available && b.supported);
    const install = overview.installs[appid];
    if (action === "remove") return install ? [{ game, choice: null }] : [];
    if (action === "install") {
      const info = compat[appid];
      return !install && preferred && info && !info.native && info.inputs.length ? [{ game, choice: defaultChoice(preferred.id) }] : [];
    }
    if (!install || !optiscaler(overview, install.build)) return [];
    if (action === "repair") return install.status === "broken" ? [{ game, choice: keep(install.options, install.build) }] : [];
    return preferred && install.build !== preferred.id && optiscaler(overview, preferred.id)
      ? [{ game, choice: keep(install.options, preferred.id) }] : [];
  });
}

function finished(job: UpscalerJob): Promise<JobUpdate> {
  return new Promise((resolve) => {
    const stop = onJobUpdate((update) => {
      if (update.job.id !== job.id || !update.finished) return;
      stop();
      resolve(update);
    });
  });
}

function failure({ job, notice }: JobUpdate): string | null {
  if (job.state !== "done") return job.error ?? "generic";
  return notice && notice.key !== "up.kept" ? "launch_failed" : null;
}

let cancelled = false;
export function cancelBulk(): void {
  cancelled = true;
}

/** One game at a time, as the backend runs one job at a time; a refusal skips that game and goes on. */
export async function runBulk(action: BulkAction, steps: BulkStep[], report: (progress: BulkProgress) => void): Promise<BulkProgress> {
  cancelled = false;
  const progress: BulkProgress = { action, index: 0, total: steps.length, current: null, done: 0, skipped: [] };
  for (const [index, step] of steps.entries()) {
    if (cancelled) break;
    const appid = String(step.game.liveAppid);
    report({ ...progress, index, current: step.game.name });
    try {
      const job = action === "remove" ? await uninstallUpscaler(appid) : await startInstallJob({ appid, liveAppid: step.game.liveAppid, isNonSteam: step.game.isNonSteam }, step.choice!);
      const result = finished(job);
      trackJob(job, { appid, liveAppid: step.game.liveAppid, isNonSteam: step.game.isNonSteam });
      const reason = failure(await result);
      if (reason) progress.skipped.push({ name: step.game.name, reason });
      else progress.done += 1;
    } catch (error) {
      progress.skipped.push({ name: step.game.name, reason: upscalerErrorCode(error) });
    }
  }
  progress.index = steps.length;
  progress.current = null;
  report({ ...progress });
  return progress;
}
