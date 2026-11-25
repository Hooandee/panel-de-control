import { recordUiEvent } from "../system/uiEvents";

export interface LosslessBranchState {
  selected: string | null;
  available: boolean;
  supported: boolean;
}

interface Details {
  strSelectedBeta?: string;
  vecBetas?: { strName?: string }[];
  eAppUpdateError?: number;
}

interface Apps {
  RegisterForAppDetails?: (appid: number, callback: (details: Details) => void) => { unregister?: () => void };
  JoinAppContentBeta?: (appid: number, branch: string) => unknown;
}

const APPID = 993090;
const BRANCH = "lsfg-vk";
const unknownState = (supported: boolean): LosslessBranchState => ({ selected: null, available: false, supported });

function observe(change: boolean, timeoutMs: number, signal?: AbortSignal): Promise<LosslessBranchState> {
  const apps = (window as unknown as { SteamClient?: { Apps?: Apps } }).SteamClient?.Apps;
  const supported = typeof apps?.RegisterForAppDetails === "function" && typeof apps.JoinAppContentBeta === "function";
  if (!apps || typeof apps.RegisterForAppDetails !== "function" || (change && !supported)) {
    if (change) recordUiEvent("upscalers", "lsfg_branch_failed", { appid: APPID, branch: BRANCH, error: "lsfg_branch_unsupported" }, false);
    return change ? Promise.reject(new Error("lsfg_branch_unsupported")) : Promise.resolve(unknownState(false));
  }
  return new Promise((resolve, reject) => {
    let done = false;
    let requested = false;
    let handle: { unregister?: () => void } | undefined;
    const cleanupHandle = () => {
      const current = handle;
      handle = undefined;
      try { current?.unregister?.(); } catch { /* Steam may already have disposed the subscription. */ }
    };
    const finish = (state?: LosslessBranchState, error?: string) => {
      if (done) return;
      done = true;
      window.clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      cleanupHandle();
      if (change) {
        if (error) recordUiEvent("upscalers", "lsfg_branch_failed", { appid: APPID, branch: BRANCH, error }, false);
        else recordUiEvent("upscalers", "lsfg_branch_confirmed", { appid: APPID, branch: BRANCH, requested });
      }
      if (error) reject(new Error(error));
      else resolve(state ?? unknownState(supported));
    };
    const abort = () => finish(undefined, "lsfg_branch_cancelled");
    const timer = window.setTimeout(() => finish(undefined, change ? "lsfg_branch_timeout" : undefined), timeoutMs);
    if (signal?.aborted) { abort(); return; }
    signal?.addEventListener("abort", abort, { once: true });
    try {
      handle = apps.RegisterForAppDetails!(APPID, (details) => {
        if (done || !details || typeof details.strSelectedBeta !== "string") return;
        const state: LosslessBranchState = {
          selected: details.strSelectedBeta,
          available: Array.isArray(details.vecBetas) && details.vecBetas.some((beta) => beta.strName === BRANCH),
          supported,
        };
        if (!change) { finish(state); return; }
        if (requested && details.eAppUpdateError) { finish(undefined, "lsfg_branch_update_failed"); return; }
        if (state.selected === BRANCH) { finish(state); return; }
        if (requested) return;
        if (!Array.isArray(details.vecBetas)) return;
        if (!state.available) { finish(undefined, "lsfg_branch_unavailable"); return; }
        requested = true;
        recordUiEvent("upscalers", "lsfg_branch_requested", { appid: APPID, branch: BRANCH });
        try {
          const result = apps.JoinAppContentBeta!(APPID, BRANCH);
          if (result === false) finish(undefined, "lsfg_branch_failed");
          else if (result && typeof (result as PromiseLike<unknown>).then === "function") {
            void Promise.resolve(result).catch(() => finish(undefined, "lsfg_branch_failed"));
          }
        } catch { finish(undefined, "lsfg_branch_failed"); }
      });
      if (done) cleanupHandle();
    } catch { finish(undefined, change ? "lsfg_branch_failed" : undefined); }
  });
}

export function readLosslessBranch(timeoutMs = 1500, signal?: AbortSignal): Promise<LosslessBranchState> {
  return observe(false, timeoutMs, signal);
}

export function switchLosslessBranch(timeoutMs = 15000, signal?: AbortSignal): Promise<LosslessBranchState> {
  return observe(true, timeoutMs, signal);
}
