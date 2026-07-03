import { useCallback, useEffect, useRef, useState } from "react";
import { Navigation, QuickAccessTab } from "@decky/ui";

import { getDevice, type DeviceInfo } from "../api";
import {
  type ColoresCardState,
  type ColoresPhase,
  coloresCardState,
  deviceHasRgb,
  installColores,
  isColoresInstalled,
  setActiveColoresPlugin,
  waitForColoresInstalled,
} from "./colores";

/**
 * Opens Colores' own Quick Access panel: switch the QAM to the Decky tab, then
 * set the active plugin on the next tick (the tab must mount before the loader
 * state renders it). Uses public `@decky/ui` Navigation here; the internal
 * loader reach is guarded in colores.ts (setActiveColoresPlugin).
 */
function openColores(): void {
  try {
    Navigation.OpenQuickAccessMenu(QuickAccessTab.Decky);
    // The Decky tab must mount before its loader state renders the active plugin;
    // try twice so a slow cold-open still lands on the Colores panel (else the
    // user just sees the Decky plugin list — a graceful degrade).
    setTimeout(setActiveColoresPlugin, 150);
    setTimeout(setActiveColoresPlugin, 500);
  } catch {
    /* no-op */
  }
}

/** Fallback when the internal install path is unavailable: open the Decky store. */
function openDeckyStore(): void {
  try {
    Navigation.Navigate("/decky/store");
  } catch {
    /* no-op */
  }
}

export interface UseColores {
  hasRgb: boolean;
  state: ColoresCardState;
  install: () => Promise<void>;
  open: () => void;
  openStore: () => void;
}

/**
 * Drives the RGB-lighting card: reads whether this device has RGB (hides on
 * Steam Deck), whether the sibling Colores plugin is installed, and runs the
 * install → verify flow. All internal Decky access is guarded in colores.ts.
 */
export function useColores(): UseColores {
  const [device, setDevice] = useState<DeviceInfo | null>(null);
  const [installed, setInstalled] = useState<boolean>(() => isColoresInstalled());
  const [phase, setPhase] = useState<ColoresPhase>("idle");
  // Decky remounts the panel each QAM open, but the install flow awaits for
  // seconds — guard so a close mid-install doesn't setState on an unmounted hook.
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);

  useEffect(() => {
    getDevice()
      .then((d) => {
        if (!mounted.current) return;
        setDevice(d);
        // Re-check once the RPC has resolved: at a cold QAM open the loader's
        // plugin list may not be populated yet at the synchronous mount read
        // above, which would otherwise show "Install" for an installed Colores.
        setInstalled(isColoresInstalled());
      })
      .catch(() => {});
  }, []);

  const install = useCallback(async () => {
    setPhase("installing");
    const ok = await installColores();
    if (!mounted.current) return;
    if (!ok) {
      setPhase("error");
      return;
    }
    // The RPC resolved; only flip to "installed" once it REALLY appears in Decky's
    // state (never-fake) — otherwise surface the honest error + store fallback.
    const found = await waitForColoresInstalled();
    if (!mounted.current) return;
    setInstalled(found);
    setPhase(found ? "idle" : "error");
  }, []);

  const hasRgb = deviceHasRgb(device);
  const state = coloresCardState({ hasRgb, installed, phase });

  return { hasRgb, state, install, open: openColores, openStore: openDeckyStore };
}
