import { getMakoStatus, getUpscalerLaunchReceipt, setMakoGame, type MakoProfile } from "../api";
import { readAppDetails } from "../launch/steamApi";
import { hasMakoLeftover } from "./makoLeftover";
import { applyManagedLaunch } from "./managedLaunch";

const writing = new Set<string>();
const token = (value: string) => /^[A-Za-z0-9_./:-]+$/.test(value) ? value : "'" + value.replace(/'/g, "'\\''") + "'";

export async function saveMakoProfile(appid: string, liveAppid: number, config: Partial<MakoProfile> | null, isNonSteam = false) {
  if (writing.has(appid)) throw new Error("mako_busy");
  writing.add(appid);
  try {
    const status = await getMakoStatus(appid);
    const previous = status?.profiles[appid] ?? null;
    if (config && !previous) {
      const [details, receipt] = await Promise.all([readAppDetails(liveAppid), getUpscalerLaunchReceipt(appid, "mako")]);
      if (!details) throw new Error("launch_failed");
      if (hasMakoLeftover(details.launch, receipt)) throw new Error("mako_foreign");
    }
    const patch = config?.scaling_enabled && !previous ? { enabled: false, ...config } : config;
    const result = await setMakoGame(appid, patch);
    let pending = false;
    try {
      const applied = await applyManagedLaunch(appid, liveAppid, "mako", {
        env: Object.fromEntries(Object.entries(result.env).map(([name, value]) => [name, token(value)])),
        wrappers: result.wrappers.map(token),
      }, { isNonSteam, requireComplete: result.profile !== null });
      pending = !!applied.pending;
      if (!applied.ok) throw new Error("launch_failed");
    } catch (error) {
      if (!pending || config === null || result.profile === null || (config.enabled === false && !previous?.scaling_enabled)) await setMakoGame(appid, previous);
      throw error;
    }
    return result.profile;
  } finally {
    writing.delete(appid);
    window.dispatchEvent(new Event("pdc-mako-changed"));
  }
}
