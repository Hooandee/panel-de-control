import { routerHook } from "@decky/api";

import { registerCatalog } from "../i18n";
import type { GameSessionPort } from "../platform/gameSessions";
import type { PowerPort } from "../platform/power";
import { AmbientRuntime } from "./steam/runtime";
import { AmbientThemeChannel } from "./steam/themeChannel";
import { FloatingPlayer } from "./ui/FloatingPlayer";
import { QamSidePlayer } from "./ui/QamSidePlayer";
import { AMBIENT_STRINGS } from "./ui/strings";
import { setAmbientRuntime } from "./ui/useAmbient";

export { AmbienteSection, AmbientPlayerBlock } from "./ui/AmbienteSection";

registerCatalog(AMBIENT_STRINGS);

/** Handed to the theme runtime host so theme runtimes can claim and host the background. */
export const ambientThemeChannel = new AmbientThemeChannel();

export interface AmbientHost {
  gameSessions: GameSessionPort;
  power: PowerPort;
  notify: (title: string, body: string) => void;
  translate: (key: string, vars?: Record<string, string>) => string;
}

/** Starts the Ambient domain at plugin load; the returned function tears it down completely. */
export function startAmbient(host: AmbientHost): () => void {
  let runtime: AmbientRuntime;
  try {
    runtime = new AmbientRuntime(host, ambientThemeChannel);
  } catch (error) {
    console.warn("[ambient:start_failed]", error);
    return () => undefined;
  }
  setAmbientRuntime(runtime);
  runtime.start().catch((error) => console.warn("[ambient:start_failed]", error));
  const sidePlayer = registerGlobal("PanelDeControlAmbientQamPlayer", QamSidePlayer);
  const floating = registerGlobal("PanelDeControlAmbientFloating", FloatingPlayer);
  return () => {
    floating();
    sidePlayer();
    setAmbientRuntime(null);
    runtime.stop();
  };
}

const Nothing = () => null;

/**
 * Decky re-renders global components only when their count changes, so a reload (old removed,
 * new added) would keep rendering the previous bundle's component. A throwaway entry added and
 * removed right after forces it to pick up the current one.
 */
function registerGlobal(name: string, component: Parameters<typeof routerHook.addGlobalComponent>[1]): () => void {
  const nudge = `${name}:refresh`;
  try {
    routerHook.addGlobalComponent(name, component);
    routerHook.addGlobalComponent(nudge, Nothing);
    setTimeout(() => {
      try {
        routerHook.removeGlobalComponent(nudge);
      } catch {
        /* router gone */
      }
    }, 0);
  } catch {
    return () => undefined;
  }
  return () => {
    try {
      routerHook.removeGlobalComponent(name);
    } catch {
      /* router already gone */
    }
  };
}
