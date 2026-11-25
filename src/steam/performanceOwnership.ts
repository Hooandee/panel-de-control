import { getGamePowerOwner } from "../api";
import { readRunningGame } from "../tdp/runningGame";
import { createPerformanceSettingsDeps } from "./performanceSettingsRuntime";
import { readPerformanceSettings, writePerformanceSetting } from "./performanceSettings";
import { readSteamPerformanceProfile, resolveSteamPerformanceStore } from "./performanceRuntime";
import { recordSteamPerformanceDiagnostic } from "./performanceDiagnostics";

let transaction: Promise<unknown> = Promise.resolve();
export function runSteamPerformanceTransaction<T>(operation: () => Promise<T>): Promise<T> {
  const next = transaction.then(operation, operation);
  transaction = next.catch(() => undefined);
  return next;
}

interface PowerSettingsStore {
  GetClientSetting: (name: string) => [unknown, (value: number | boolean) => unknown];
}

async function reapplyPowerSettings(stableAppid: string | null, liveAppid: number | null, alive: () => boolean): Promise<boolean> {
  const sameContext = () => {
    const current = readRunningGame();
    return alive() && (current?.appid ?? null) === stableAppid && (current?.liveAppid ?? null) === liveAppid;
  };
  if (!sameContext()) return false;
  const state = await getGamePowerOwner();
  if (!sameContext() || state.context_appid !== stableAppid || state.owner !== "steam"
    || state.supported !== true) return false;
  const capabilities = createPerformanceSettingsDeps().steamOs() as Record<string, unknown> | null;
  const store = (globalThis as unknown as { window?: { settingsStore?: PowerSettingsStore } }).window?.settingsStore;
  if (!capabilities || typeof store?.GetClientSetting !== "function") return false;
  let requested = false;
  for (const [capability, valueKey, enabledKey] of [
    ["is_tdp_limit_available", "steamos_tdp_limit", "steamos_tdp_limit_enabled"],
    ["is_manual_gpu_clock_available", "steamos_manual_gpu_clock_hz", "steamos_manual_gpu_clock_enabled"],
  ]) {
    if (!sameContext()) return requested;
    if (capabilities[capability] !== true) continue;
    const [enabled, setEnabled] = store.GetClientSetting(enabledKey);
    const [value, setValue] = store.GetClientSetting(valueKey);
    if (typeof enabled !== "boolean" || typeof setEnabled !== "function") continue;
    const validValue = typeof value === "number" && Number.isFinite(value) && Number.isInteger(value) && value > 0;
    if (enabled && (!validValue || typeof setValue !== "function")) continue;
    if (validValue && typeof setValue === "function") {
      if (!sameContext()) return requested;
      await setValue(value);
      requested = true;
    }
    if (!sameContext()) return requested;
    await setEnabled(enabled);
    requested = true;
  }
  if (requested) recordSteamPerformanceDiagnostic("control", { status: "steam_power_reapply_requested" });
  return requested;
}

export async function reapplyResetPowerSettings(stableAppid: string | null, liveAppid: number | null, isCurrent: () => boolean): Promise<boolean> {
  const sameContext = () => {
    const current = readRunningGame();
    return isCurrent() && (current?.appid ?? null) === stableAppid && (current?.liveAppid ?? null) === liveAppid;
  };
  if (!sameContext()) return false;
  const state = await getGamePowerOwner();
  if (!sameContext() || state.context_appid !== stableAppid || !state.reset_pending || state.supported !== true) return false;
  const capabilities = createPerformanceSettingsDeps().steamOs() as Record<string, unknown> | null;
  const store = (globalThis as unknown as { window?: { settingsStore?: PowerSettingsStore } }).window?.settingsStore;
  if (!capabilities || typeof store?.GetClientSetting !== "function") return false;
  const setters: Array<(value: boolean) => unknown> = [];
  for (const [capability, key] of [
    ["is_tdp_limit_available", "steamos_tdp_limit_enabled"],
    ["is_manual_gpu_clock_available", "steamos_manual_gpu_clock_enabled"],
  ]) {
    if (typeof capabilities[capability] !== "boolean") return false;
    if (capabilities[capability] === false) continue;
    const [enabled, setEnabled] = store.GetClientSetting(key);
    if (typeof enabled !== "boolean" || typeof setEnabled !== "function") return false;
    setters.push(setEnabled);
  }
  if (!setters.length) return false;
  for (const setEnabled of setters) {
    if (!sameContext()) return false;
    await setEnabled(false);
  }
  if (!sameContext()) return false;
  recordSteamPerformanceDiagnostic("control", { status: "steam_power_reset_requested" });
  return true;
}

export async function reapplySteamPowerSettings(stableAppid: string, liveAppid: number): Promise<boolean> {
  try { return await reapplyPowerSettings(stableAppid, liveAppid, () => true); }
  catch { recordSteamPerformanceDiagnostic("control", { status: "steam_power_reapply_failed" }); return false; }
}

export function startSteamPerformanceOwnership(): () => void {
  let alive = true;
  let pending = false;
  let enteredOwner: string | null = null;
  const deps = createPerformanceSettingsDeps();
  const reconcile = () => {
    if (!alive || pending) return;
    pending = true;
    void runSteamPerformanceTransaction(async () => {
      const game = readRunningGame();
      if (!alive || !game) { enteredOwner = null; return; }
      const sameContext = () => {
        const current = readRunningGame();
        return alive && current?.appid === game.appid && current.liveAppid === game.liveAppid;
      };
      const state = await getGamePowerOwner();
      if (!sameContext() || state.context_appid !== game.appid || state.reset_pending) return;
      const ownerKey = `${game.appid}:${game.liveAppid}:${state.owner}`;
      if (state.owner === "steam") {
        if (enteredOwner !== ownerKey && await reapplyPowerSettings(game.appid, game.liveAppid, () => alive)) enteredOwner = ownerKey;
        return;
      }
      enteredOwner = ownerKey;
      if (state.explicit_owner !== "pdc"
        || state.supported !== true) return;
      const profile = readSteamPerformanceProfile(game.liveAppid);
      if (profile === "unknown") return;
      if (profile === "global") {
        const store = resolveSteamPerformanceStore();
        if (typeof store?.SetGameSpecificProfileEnabled !== "function") return;
        store.SetGameSpecificProfileEnabled(true);
        recordSteamPerformanceDiagnostic("control", { status: "profile_reapply_requested" });
        return;
      }
      for (const control of readPerformanceSettings(deps)) {
        if (!sameContext()) return;
        if (control.kind === "action") continue;
        const expected = state.steam_settings?.[control.id];
        if (expected === undefined || expected === control.value) continue;
        const result = await writePerformanceSetting(deps, { scope: "game", runningGameId: game.liveAppid }, control.id, expected);
        recordSteamPerformanceDiagnostic("control", { status: `reconcile_${result.status}`, control_id: control.id });
      }
    }).catch(() => {
      if (alive) recordSteamPerformanceDiagnostic("control", { status: "ownership_unavailable" });
    }).finally(() => { pending = false; });
  };
  const timer = setInterval(reconcile, 2000);
  reconcile();
  return () => { alive = false; clearInterval(timer); };
}
