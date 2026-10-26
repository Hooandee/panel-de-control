import { abortGamePowerReset, beginGamePowerReset, finishGamePowerReset, type GamePowerOwnerState } from "../api";
import { readPerformanceSettings, writePerformanceSetting, type PerformanceEditContext, type PerformanceSettingsDeps } from "./performanceSettings";
import { reapplyResetPowerSettings } from "./performanceOwnership";
import { subscribeSteamPerformanceState } from "./performanceRuntime";

export async function resetManagedGamePerformance(
  deps: PerformanceSettingsDeps,
  context: PerformanceEditContext,
  owner: GamePowerOwnerState,
  isCurrent: () => boolean,
) {
  if (!isCurrent() || (context.scope === "game" && !owner.context_appid) || !readPerformanceSettings(deps).some(({ id }) => id === "reset")) {
    throw new Error("reset_unavailable");
  }
  const begun = await beginGamePowerReset(owner.context_appid, owner.revision);
  if (!begun.ok || !begun.token) throw new Error(begun.detail ?? "reset_unavailable");
  let completed = false;
  let unsubscribe = () => {};
  let timer: ReturnType<typeof setInterval> | undefined;
  try {
    if (!isCurrent()) throw new Error("stale_context");
    let requested = false;
    let acknowledged = false;
    unsubscribe = subscribeSteamPerformanceState(() => {
      if (requested) acknowledged = true;
    });
    await Promise.resolve();
    requested = true;
    const written = await writePerformanceSetting(deps, context, "reset");
    if (written.status !== "request_sent") throw new Error(written.status);
    const settings = await new Promise<Record<string, number | boolean>>((resolve, reject) => {
      const deadline = Date.now() + 5000;
      let stableSince = 0;
      let signature = "";
      timer = setInterval(() => {
        try {
          if (!isCurrent()) throw new Error("stale_context");
          if (Date.now() >= deadline) throw new Error("reset_readback_timeout");
          if (!acknowledged) return;
          const values = Object.fromEntries(readPerformanceSettings(deps).flatMap((control) =>
            control.kind === "action" ? [] : [[control.id, control.value]],
          ));
          if (!Object.keys(values).length) throw new Error("reset_readback_unavailable");
          const next = JSON.stringify(values);
          if (next !== signature) { signature = next; stableSince = Date.now(); return; }
          if (Date.now() - stableSince >= 250) resolve(values);
        } catch (error) { reject(error); }
      }, 50);
    });
    if (!isCurrent()) throw new Error("stale_context");
    if (!await reapplyResetPowerSettings(owner.context_appid, context.runningGameId, isCurrent)) throw new Error("reset_power_unavailable");
    if (!isCurrent()) throw new Error("stale_context");
    const result = await finishGamePowerReset(begun.token, settings);
    if (!result.ok) throw new Error(result.detail ?? "reset_save_failed");
    completed = true;
    return result;
  } finally {
    if (timer !== undefined) clearInterval(timer);
    unsubscribe();
    if (!completed) await abortGamePowerReset(begun.token).catch(() => undefined);
  }
}
