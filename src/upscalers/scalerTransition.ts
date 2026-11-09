import { beginScalerTransition, finishScalerTransition, getMakoStatus, type MakoProfile } from "../api";
import { applyManagedLaunch } from "./managedLaunch";
import { saveMakoProfile } from "./makoProfile";
import { launchAfterJob } from "./model";
import type { JobGame } from "./jobRunner";

const switching = new Set<string>();
export const scalerSwitching = (appid: string) => switching.has(appid);
function changed() { if (typeof window !== "undefined") window.dispatchEvent(new Event("pdc-scaler-switch")); }
export function lockScalerSwitch(appid: string): () => void {
  if (switching.has(appid)) throw new Error("busy");
  switching.add(appid); changed();
  return () => { switching.delete(appid); changed(); };
}

export interface ScalerTransition { finish: (success: boolean) => Promise<void> }
export async function prepareScalerTransition(game: JobGame, direction: "mako" | "installed", required = false): Promise<ScalerTransition | null> {
  const release = lockScalerSwitch(game.appid);
  let previous: MakoProfile | null = null;
  let token: string | null = null;
  const rollback = async () => {
    const restore = await finishScalerTransition(game.appid, token!, true);
    if (restore) {
      const env = Object.fromEntries(Object.entries(restore.env ?? {}).filter((pair): pair is [string, string] => pair[1] !== null));
      const launch = await applyManagedLaunch(game.appid, game.liveAppid, "upscaler", { env }, {
        isNonSteam: game.isNonSteam, requireComplete: true,
        transform: value => launchAfterJob(value, { ...restore, env: undefined }, "install")?.value ?? null,
      });
      if (!launch.ok) throw new Error("transition_restore_failed");
    }
    await saveMakoProfile(game.appid, game.liveAppid, previous, game.isNonSteam);
    await finishScalerTransition(game.appid, token!, false);
  };
  try {
    const status = await getMakoStatus(game.appid);
    previous = status.profiles[game.appid] ?? null;
    if (direction === "installed" && !required && !previous?.scaling_enabled && !status.scaler_transition_pending) { release(); return null; }
    const checkpoint = await beginScalerTransition(game.appid);
    token = checkpoint.token;
    previous = checkpoint.previous_mako;
    if (checkpoint.recovery) {
      await rollback();
      token = null;
      throw new Error("transition_recovered");
    }
    if (direction === "installed" && previous?.scaling_enabled) await saveMakoProfile(game.appid, game.liveAppid, { scaling_enabled: false }, game.isNonSteam);
    return { finish: async success => {
      try {
        if (success) {
          try { await finishScalerTransition(game.appid, token!, false); }
          catch {
            try { await rollback(); } catch { throw new Error("transition_restore_failed"); }
            throw new Error("transition_failed");
          }
        } else await rollback();
      } catch (error) {
        if (!success) throw new Error("transition_restore_failed");
        throw error;
      } finally { release(); }
    } };
  } catch (error) {
    try { if (token) await rollback(); }
    catch { throw new Error("transition_restore_failed"); }
    finally { release(); }
    throw error;
  }
}
