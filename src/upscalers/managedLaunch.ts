import { getUpscalerLaunchReceipt, setUpscalerLaunchReceipt } from "../api";
import { readAppDetails, writeLaunchOptions } from "../launch/steamApi";
import { recordUiEvent } from "../system/uiEvents";
import { planLaunchOverlay, type LaunchOverlay, type LaunchOverlayPlan, type LaunchReceipt } from "./launchOwnership";

export interface ManagedLaunchResult {
  ok: boolean;
  pending?: boolean;
  preserved: LaunchOverlayPlan["preserved"];
}
export interface ManagedLaunchOptions {
  isNonSteam?: boolean;
  transform?: (launch: string) => string | null;
  requireComplete?: boolean;
  beforeApply?: () => Promise<void>;
}

const writing = new Set<string>();

async function confirmed(liveAppid: number, value: string): Promise<boolean> {
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt) await new Promise((resolve) => setTimeout(resolve, 120));
    if ((await readAppDetails(liveAppid, 400).catch(() => null))?.launch === value) return true;
  }
  return false;
}

function intentReceipt(previous: LaunchReceipt | null, next: LaunchReceipt): LaunchReceipt {
  const env = new Map(previous?.env.map(entry => [entry.name, entry]) ?? []);
  for (const entry of next.env) env.set(entry.name, entry);
  return {
    ...next,
    pending: true,
    env: [...env.values()],
    wrappers: next.wrappers.added.length ? next.wrappers : previous?.wrappers ?? next.wrappers,
  };
}

export async function applyManagedLaunch(appid: string, liveAppid: number, owner: "lsfg" | "mako" | "upscaler", desired: LaunchOverlay, options: ManagedLaunchOptions = {}): Promise<ManagedLaunchResult> {
  let preserved: ManagedLaunchResult["preserved"] = { env: [], wrappers: [] };
  let pending = false;
  const finish = (ok: boolean, reason: string): ManagedLaunchResult => {
    recordUiEvent("upscalers", "launch", { appid: liveAppid, owner, reason, preservedEnv: preserved.env.length, preservedWrappers: preserved.wrappers.length }, ok);
    return { ok, preserved, ...(pending ? { pending: true } : {}) };
  };
  if (writing.has(appid)) return finish(false, "busy");
  writing.add(appid);
  try {
    const [details, receipt] = await Promise.all([readAppDetails(liveAppid), getUpscalerLaunchReceipt(appid, owner)]);
    pending = !!receipt?.pending;
    if (!details) return finish(false, "unreadable");
    const transformed = options.transform ? options.transform(details.launch) : details.launch;
    const plan = transformed === null ? null : planLaunchOverlay(transformed, desired, receipt);
    if (!plan) return finish(false, "ambiguous");
    preserved = plan.preserved;
    if (options.requireComplete && (preserved.env.length || preserved.wrappers.length)) return finish(false, "external_parameters");
    if ((await readAppDetails(liveAppid))?.launch !== details.launch) return finish(false, "changed_during_read");
    await options.beforeApply?.();
    const nonSteam = options.isNonSteam ?? (appid.startsWith("ns:") || liveAppid > 0x7fffffff);
    if (plan.value !== details.launch) {
      const savedIntent = await setUpscalerLaunchReceipt(appid, owner, intentReceipt(receipt, plan.receipt)).catch(() => false);
      if (!savedIntent) return finish(false, "intent_failed");
      if ((await readAppDetails(liveAppid).catch(() => null))?.launch !== details.launch) {
        await setUpscalerLaunchReceipt(appid, owner, receipt ?? { version: 1, env: [], wrappers: { before: [], applied: [], added: [] } }).catch(() => false);
        return finish(false, "changed_before_write");
      }
      pending = true;
      if (!writeLaunchOptions(liveAppid, plan.value, nonSteam, true)) return finish(false, "write_unconfirmed");
      if (!await confirmed(liveAppid, plan.value)) return finish(false, "unconfirmed");
    }
    const saved = await setUpscalerLaunchReceipt(appid, owner, plan.receipt).catch(() => false);
    if (!saved) return finish(false, "receipt_failed");
    pending = false;
    return finish(true, "confirmed");
  } catch {
    return finish(false, "unavailable");
  } finally {
    writing.delete(appid);
  }
}
