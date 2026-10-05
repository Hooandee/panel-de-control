import { addEventListener, removeEventListener } from "@decky/api";
import { Navigation } from "@decky/ui";

import { getKioskState, kioskSteamResult } from "../api";
import { callBackend } from "../deckyInternal";
import { displayBrightness } from "../system/display";
import { systemVolume } from "../system/audio";
import { resolveSteamPerformanceStore } from "../steam/performanceRuntime";
import { steamDeckPerf } from "./deckPerf";
import type { ScalarControl } from "../system/types";
import {
  COLORES_PLUGIN_NAME,
  installColores,
  isColoresInstalled,
  waitForColoresInstalled,
} from "../system/colores";

// Must match py_modules/kiosk/bridge.py (EVENT and ACTIONS).
export const KIOSK_STEAM_EVENT = "pdc_kiosk_steam";

type Handler = (args: unknown[]) => unknown | Promise<unknown>;

// Colores RPCs the bottom screen may drive; everything else stays in Colores' own UI.
export const COLORES_METHODS = new Set([
  "get_state", "set_power", "set_brightness", "set_mode", "set_solid", "set_effect",
  "set_gradient", "set_gradient_speed", "patch_profile",
]);

interface PerfStore {
  msgLimits?: {
    is_manual_display_refresh_rate_available?: boolean;
    display_refresh_manual_hz_min?: number;
    display_refresh_manual_hz_max?: number;
    disable_refresh_rate_management?: boolean;
  };
  msgSettingsPerApp?: { display_refresh_manual_hz?: number };
  SetDisplayRefreshRateManualHz?: (hz: number) => unknown;
}

export interface BridgeDeps {
  perf: Record<string, Handler>;
  brightness: ScalarControl;
  volume: ScalarControl;
  perfStore: () => PerfStore | null;
  showKeyboard: () => boolean;
  takeScreenshot: () => boolean;
  openQuickAccess: () => void;
  colores: {
    installed: () => boolean;
    call: (method: string, args: unknown[]) => Promise<unknown>;
    install: () => Promise<boolean>;
  };
}


const fraction = (value: unknown): number => {
  const n = Number(value);
  if (!Number.isFinite(n)) throw new Error("bad_value");
  return Math.max(0, Math.min(1, n));
};

/** Last value Steam reported for a scalar; Steam only pushes changes, it has no getter. */
function follow(control: ScalarControl): { read: () => number | null; stop: () => void } {
  let value: number | null = null;
  const stop = control.subscribe((next) => {
    value = next;
  });
  return { read: () => value, stop: stop ?? (() => {}) };
}

export function createBridgeHandlers(deps: BridgeDeps): { handlers: Record<string, Handler>; stop: () => void } {
  const brightness = follow(deps.brightness);
  const volume = follow(deps.volume);

  const refresh = () => {
    const store = deps.perfStore();
    const limits = store?.msgLimits;
    if (!store || !limits?.is_manual_display_refresh_rate_available) return null;
    return {
      current: store.msgSettingsPerApp?.display_refresh_manual_hz ?? null,
      min: limits.display_refresh_manual_hz_min ?? null,
      max: limits.display_refresh_manual_hz_max ?? null,
      // Steam reports the range but will not switch modes (AYN Thor under gamescope 3.16).
      settable: !limits.disable_refresh_rate_management,
      store,
    };
  };

  const handlers: Record<string, Handler> = {
    "brightness.get": () => ({ value: brightness.read() }),
    "brightness.set": ([value]) => {
      deps.brightness.set(fraction(value));
      return true;
    },
    "volume.get": () => ({ value: volume.read() }),
    "volume.set": ([value]) => {
      deps.volume.set(fraction(value));
      return true;
    },
    "refresh.get": () => {
      const r = refresh();
      return r ? { current: r.current, min: r.min, max: r.max, settable: r.settable } : null;
    },
    "refresh.set": ([value]) => {
      const r = refresh();
      const hz = Math.round(Number(value));
      if (!r?.settable || !r.store.SetDisplayRefreshRateManualHz || r.min == null || r.max == null) throw new Error("unsupported");
      if (!Number.isFinite(hz) || hz < r.min || hz > r.max) throw new Error("bad_value");
      r.store.SetDisplayRefreshRateManualHz(hz);
      return true;
    },
    screenshot: () => {
      if (!deps.takeScreenshot()) throw new Error("unsupported");
      return true;
    },
    keyboard: () => {
      if (!deps.showKeyboard()) throw new Error("unsupported");
      return true;
    },
    quick_access: () => {
      deps.openQuickAccess();
      return true;
    },
    "colores.state": async () => {
      if (!deps.colores.installed()) return { installed: false };
      return { installed: true, state: await deps.colores.call("get_state", []) };
    },
    "colores.call": async ([method, args]) => {
      if (typeof method !== "string" || !COLORES_METHODS.has(method)) throw new Error("unknown_method");
      if (!deps.colores.installed()) throw new Error("not_installed");
      return deps.colores.call(method, Array.isArray(args) ? args : []);
    },
    "colores.install": () => deps.colores.install(),
    ...deps.perf,
  };

  // The native bottom screen polls everything at once: one round trip through Steam instead of five.
  const settle = async (action: string) => {
    try {
      return { ok: true, result: (await handlers[action]([])) ?? null };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  };
  handlers.snapshot = async () => {
    const actions = ["brightness.get", "volume.get", "refresh.get", "perf.view", "colores.state"].filter((a) => handlers[a]);
    return Object.fromEntries(await Promise.all(actions.map(async (action) => [action, await settle(action)])));
  };

  return {
    handlers,
    stop: () => {
      brightness.stop();
      volume.stop();
    },
  };
}

interface SteamWindowGlobals {
  SteamUIStore?: {
    m_WindowStore?: {
      MainWindowInstance?: { m_VirtualKeyboardManager?: { SetVirtualKeyboardVisible?: () => void } };
    };
  };
  g_GRS?: { TakeScreenshot?: () => unknown };
}

export function steamDeps(host: Window = window): BridgeDeps {
  const globals = host as unknown as SteamWindowGlobals;
  return {
    perf: steamDeckPerf(),
    brightness: displayBrightness,
    volume: systemVolume,
    perfStore: () => (resolveSteamPerformanceStore() as PerfStore | null),
    showKeyboard: () => {
      const keyboard = globals.SteamUIStore?.m_WindowStore?.MainWindowInstance?.m_VirtualKeyboardManager;
      if (typeof keyboard?.SetVirtualKeyboardVisible !== "function") return false;
      keyboard.SetVirtualKeyboardVisible();
      return true;
    },
    takeScreenshot: () => {
      if (typeof globals.g_GRS?.TakeScreenshot !== "function") return false;
      globals.g_GRS.TakeScreenshot();
      return true;
    },
    openQuickAccess: () => Navigation.OpenQuickAccessMenu(),
    colores: {
      installed: isColoresInstalled,
      call: (method, args) => callBackend("loader/call_plugin_method", COLORES_PLUGIN_NAME, method, ...args),
      install: async () => (await installColores()) && (await waitForColoresInstalled()),
    },
  };
}

/** Serve the bottom screen's Steam-only requests for as long as the plugin is loaded. */
export function startKioskSteamBridge(deps: BridgeDeps = steamDeps()): () => void {
  const { handlers, stop } = createBridgeHandlers(deps);
  const listener = async (requestId: number, action: string, args: unknown[]) => {
    const handler = handlers[action];
    try {
      if (!handler) throw new Error("unknown_action");
      await kioskSteamResult(requestId, true, (await handler(args ?? [])) ?? null);
    } catch (error) {
      await kioskSteamResult(requestId, false, error instanceof Error ? error.message : String(error)).catch(() => {});
    }
  };
  addEventListener(KIOSK_STEAM_EVENT, listener);
  return () => {
    removeEventListener(KIOSK_STEAM_EVENT, listener);
    stop();
  };
}

/** Starts the bridge only on machines that have a bottom screen; the rest never subscribe to Steam. */
export function startKioskSteamBridgeWhenSupported(
  supported: () => Promise<boolean> = () => getKioskState().then((state) => state.supported),
  start: () => () => void = startKioskSteamBridge,
): () => void {
  let stop: (() => void) | null = null;
  let stopped = false;
  supported().then((yes) => {
    if (yes && !stopped) stop = start();
  }).catch(() => {});
  return () => {
    stopped = true;
    stop?.();
  };
}
