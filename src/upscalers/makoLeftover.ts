import { useCallback, useEffect, useState } from "react";
import { getUpscalerLaunchReceipt } from "../api";
import { parse, serialize, setEnv } from "../launch/compose";
import { readAppDetails, writeLaunchOptions } from "../launch/steamApi";
import { recordUiEvent } from "../system/uiEvents";
import { configuredLaunchTools } from "./launchTools";
import type { LaunchReceipt } from "./launchOwnership";

const WRAPPERS = ["mako-run", "mako-launch", "mako-framegen"];
const ENVS = ["MAKO_CONFIG", "MAKO_PROFILE"];

export function isMakoWrapper(token: string): boolean {
  return WRAPPERS.includes(token.replace(/^(["'])(.*)\1$/, "$2").split("/").pop() ?? "");
}

/** Mako in the launch options that Panel did not put there: another tool's setup for this game. */
export function hasMakoLeftover(launch: string, receipt: LaunchReceipt | null | undefined): boolean {
  return !receipt?.wrappers.added.length && configuredLaunchTools(launch).includes("Mako");
}

const unquote = (value: string) => value.replace(/^(["'])(.*)\1$/, "$2");

/** The values Panel itself writes for one Mako profile `pdc-<id>`, so nobody else's setup is ever mistaken for it. */
function isPanelMakoValue(name: string, value: string, id: string): boolean {
  const plain = unquote(value);
  const folder = `/panel-de-control/mako/${id}/`;
  if (name === "MAKO_PROFILE") return plain === `pdc-${id}`;
  if (name === "MAKO_CONFIG") return plain.endsWith(`${folder}conf.toml`);
  if (name === "MAKO_LAUNCH_CONFIG") return plain.endsWith(`${folder}launcher.conf`);
  return false;
}

/**
 * A receipt for Panel's own Mako options in place, as if Panel had just written them; null when anything Mako there
 * is not exactly what Panel writes for one of its profiles (another profile or path, a Mako wrapper with its own
 * flags). The profile id comes from the options themselves: shortcuts use their launch identity, not their appid.
 */
export function adoptedMakoReceipt(launch: string): LaunchReceipt | null {
  const parsed = parse(launch);
  if (parsed.malformed) return null;
  const added = parsed.wrappers.filter(isMakoWrapper);
  if (added.length !== 1 || !/\/panel-de-control\/mako\/[^/]+\/bin\/mako-launch$/.test(unquote(added[0]))) return null;
  const at = parsed.wrappers.indexOf(added[0]);
  if (parsed.wrappers[at + 1]?.startsWith("-")) return null;
  const env = parsed.envs.filter((entry) => entry.name.startsWith("MAKO_"));
  const id = unquote(env.find((entry) => entry.name === "MAKO_PROFILE")?.value ?? "").match(/^pdc-([A-Za-z0-9_.:-]+)$/)?.[1];
  if (!id || !env.every((entry) => isPanelMakoValue(entry.name, entry.value, id))) return null;
  return {
    version: 1,
    env: env.map((entry) => ({ name: entry.name, before: null, applied: entry.value })),
    wrappers: { before: parsed.wrappers.filter((token) => token !== added[0]), applied: [...parsed.wrappers], added },
  };
}

/** The launch options without Mako's wrapper, its own flags and its variables; null when there is nothing safe to take out. */
export function withoutMako(launch: string): string | null {
  let parsed = parse(launch);
  if (parsed.malformed) return null;
  const wrappers: string[] = [];
  let dropping = false;
  for (const token of parsed.wrappers) {
    if (isMakoWrapper(token)) { dropping = true; continue; }
    if (dropping && token.startsWith("-")) continue;
    dropping = false;
    wrappers.push(token);
  }
  parsed = { ...parsed, wrappers };
  for (const name of ENVS) parsed = setEnv(parsed, name, null);
  const value = serialize(parsed);
  return value === serialize(parse(launch)) ? null : value;
}

export async function clearMakoLeftover(liveAppid: number, isNonSteam: boolean): Promise<boolean> {
  const details = await readAppDetails(liveAppid);
  const value = details ? withoutMako(details.launch) : null;
  let ok = false;
  if (value !== null && writeLaunchOptions(liveAppid, value, isNonSteam, true)) {
    // Steam takes a moment to hand the new options back.
    for (let attempt = 0; attempt < 6 && !ok; attempt++) {
      if (attempt) await new Promise((resolve) => setTimeout(resolve, 150));
      ok = (await readAppDetails(liveAppid, 400).catch(() => null))?.launch === value;
    }
  }
  recordUiEvent("upscalers", "mako_leftover_clear", { appid: liveAppid }, ok);
  return ok;
}

export function useMakoLeftover(appid: string, liveAppid: number, isNonSteam: boolean) {
  const [leftover, setLeftover] = useState(false);
  const check = useCallback(async () => {
    try {
      const [details, receipt] = await Promise.all([readAppDetails(liveAppid), getUpscalerLaunchReceipt(appid, "mako")]);
      return !!details && hasMakoLeftover(details.launch, receipt);
    } catch { return false; }
  }, [appid, liveAppid]);
  useEffect(() => {
    let alive = true;
    const refresh = () => { void check().then((next) => { if (alive) setLeftover(next); }); };
    setLeftover(false);
    refresh();
    window.addEventListener("pdc-mako-changed", refresh);
    return () => { alive = false; window.removeEventListener("pdc-mako-changed", refresh); };
  }, [check]);
  const clear = useCallback(async () => {
    const ok = await clearMakoLeftover(liveAppid, isNonSteam);
    setLeftover(await check());
    window.dispatchEvent(new Event("pdc-mako-changed"));
    if (!ok) throw new Error("launch_failed");
  }, [check, liveAppid, isNonSteam]);
  return { leftover, clear };
}
