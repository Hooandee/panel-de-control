import { findSP } from "@decky/ui";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { readThemeHealth } from "./themeCleanupHost";
import {
  cleanupNeeded,
  cleanupPlan,
  diagnoseThemeHealth,
  hooandeeNames,
  readSteamSettings,
  steamDisplayState,
  type SteamDisplayState,
  type ThemeCleanupPlan,
  type ThemeHealthBackend,
  type ThemeHealthFinding,
} from "./themeHealth";
import type { ThemesController } from "./useThemes";

export interface ThemeHealthView {
  checking: boolean;
  unavailable: boolean;
  findings: ThemeHealthFinding[];
  plan: ThemeCleanupPlan | null;
  needsCleanup: boolean;
  undo: ThemeHealthBackend["undo"] | null;
  display: SteamDisplayState | null;
  recheck(): Promise<void>;
  cleanUp(): Promise<boolean>;
  undoCleanup(): Promise<boolean>;
}

export async function readSteamDisplay(): Promise<SteamDisplayState> {
  const steam = typeof SteamClient === "undefined" ? undefined : SteamClient;
  const settings = await readSteamSettings(steam?.Settings as Parameters<typeof readSteamSettings>[0]);
  let view: Window | null = null;
  try {
    view = findSP() ?? null;
  } catch {}
  return steamDisplayState(settings, view);
}

export function useThemeHealth(controller: ThemesController): ThemeHealthView {
  const [backend, setBackend] = useState<ThemeHealthBackend | null>(null);
  const [display, setDisplay] = useState<SteamDisplayState | null>(null);
  const [checking, setChecking] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const request = useRef(0);

  const recheck = useCallback(async () => {
    const current = ++request.current;
    setChecking(true);
    const [health, steamDisplay] = await Promise.all([
      readThemeHealth().catch(() => null),
      readSteamDisplay(),
    ]);
    if (current !== request.current) return;
    setBackend(health);
    setUnavailable(health === null);
    setDisplay(steamDisplay);
    setChecking(false);
  }, []);

  useEffect(() => {
    void recheck();
  }, [recheck]);

  const keep = useMemo(
    () => backend ? hooandeeNames(backend, controller.cards.map((card) => card.release.cssLoaderName)) : null,
    [backend, controller.cards],
  );
  const findings = useMemo(
    () => backend && display && keep ? diagnoseThemeHealth(controller.snapshot, backend, display, keep) : [],
    [backend, display, keep, controller.snapshot],
  );
  const plan = useMemo(
    () => keep ? cleanupPlan(controller.snapshot, findings, keep) : null,
    [controller.snapshot, findings, keep],
  );

  const run = useCallback(async (action: (keep: readonly string[]) => Promise<boolean>) => {
    if (!keep) return false;
    const ok = await action([...keep]);
    await recheck();
    return ok;
  }, [keep, recheck]);

  return {
    checking,
    unavailable,
    findings,
    plan,
    needsCleanup: plan !== null && cleanupNeeded(plan),
    undo: backend?.undo ?? null,
    display,
    recheck,
    cleanUp: () => run(controller.cleanUp),
    undoCleanup: () => run(controller.undoCleanup),
  };
}
